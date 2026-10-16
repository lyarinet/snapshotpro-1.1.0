import time
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QThreadPool, Qt
from PyQt6.QtGui import QColor, QImage, QKeySequence, QPixmap
from PyQt6.QtTest import QTest
from snapshot_pro import (AnnotationItem, CaptureOverlay, OCRResultDialog, SettingsDialog,
                          SnapShotController, ScrollingCaptureController, ToolType)
from snapshot_native import windows_hotkey, qt_to_pynput_key


def overlay_for(config, width=640, height=480, dpr=1):
    pixmap = QPixmap(round(width*dpr), round(height*dpr)); pixmap.fill(QColor('white'))
    pixmap.setDevicePixelRatio(dpr)
    overlay = CaptureOverlay(pixmap, QRect(-640, 40, width, height), config)
    overlay.selection_rect = QRect(30, 25, 200, 140)
    return overlay


def test_annotation_export_hidpi_and_solid_redaction(app, config):
    overlay = overlay_for(config, dpr=2)
    overlay.annotations.append(AnnotationItem(ToolType.REDACT, QColor('black'), 4,
                                             QPoint(50, 45), QPoint(100, 75)))
    result = overlay.render_final_crop().toImage()
    assert (result.width(), result.height()) == (400, 280)
    assert result.pixelColor(60, 60) == QColor('black')
    assert result.pixelColor(5, 5) == QColor('white')
    # No drawing into the shared source image.
    assert overlay.working_pixmap.toImage().pixelColor(100, 100) == QColor('white')
    overlay.close()


def test_every_annotation_tool_exports(app, config):
    overlay = overlay_for(config)
    for tool in ToolType:
        if tool == ToolType.SELECT_MOVE:
            continue
        overlay.annotations = [AnnotationItem(tool, QColor('red'), 4, QPoint(60, 60),
                                              QPoint(100, 100), [QPoint(60, 60), QPoint(100, 100)], 'Test', 1)]
        assert not overlay.render_final_crop().isNull()
    overlay.close()


def test_no_selection_does_not_copy_entire_desktop(app, config):
    overlay = overlay_for(config)
    app.clipboard().setText('keep')
    overlay.selection_rect = QRect()
    overlay.action_copy_clipboard()
    assert app.clipboard().text() == 'keep'
    assert overlay.render_final_crop().isNull()
    overlay.close()


def test_scroll_request_uses_global_negative_origin(app, config):
    overlay = overlay_for(config)
    targets = []; overlay.scroll_capture_requested.connect(targets.append)
    overlay.action_start_scroll_capture()
    assert targets == [QRect(-610, 65, 200, 140)]


def test_toolbars_stay_inside_small_screens(app, config):
    for width, height in ((640,480), (800,600), (360,640)):
        overlay = overlay_for(config, width, height)
        overlay.editor_mode = True
        overlay.selection_rect = QRect(0,0,width,height)
        overlay._position_toolbars()
        assert overlay.rect().contains(overlay.tools_bar.geometry())
        assert overlay.rect().contains(overlay.actions_bar.geometry())
        overlay.close()


def test_multisnip_toggle_and_step_undo_redo(app, config):
    overlay = overlay_for(config)
    overlay._toggle_multi_mode(); assert overlay.multi_mode and overlay.multi_btn.isChecked()
    overlay._toggle_multi_mode(); assert not overlay.multi_mode and not overlay.multi_btn.isChecked()
    overlay.annotations = [AnnotationItem(ToolType.STEP_COUNTER,QColor('red'),4,step_number=1)]
    overlay.undo_annotation(); assert overlay.step_counter_value == 1
    overlay.redo_annotation(); assert overlay.step_counter_value == 2
    overlay.close()


def test_reset_then_cancel_preserves_settings(app, config):
    config.hotkey_region = 'F9'; config.show_magnifier = False
    dialog = SettingsDialog(config)
    dialog._reset_defaults(); dialog.reject()
    assert config.hotkey_region == 'F9'
    assert config.show_magnifier is False


def test_duplicate_hotkeys_do_not_overwrite_settings(app, config, monkeypatch):
    messages=[]
    monkeypatch.setattr('snapshot_pro.QMessageBox.warning', lambda *args: messages.append(args[2]))
    dialog=SettingsDialog(config)
    dialog.primary_key_edit.setKeySequence(QKeySequence('F9'))
    dialog.secondary_key_edit.setKeySequence(QKeySequence('F9'))
    dialog._save_settings()
    assert messages and config.hotkey_region == 'Print'
    dialog.reject()


def test_native_hotkey_translation():
    assert windows_hotkey('Ctrl+Shift+S') == (0x4006, ord('S'))
    assert windows_hotkey('Print') == (0x4000, 0x2C)
    assert windows_hotkey('Alt+F12') == (0x4001, 0x7B)
    assert qt_to_pynput_key('Ctrl+Shift+S') == '<ctrl>+<shift>+s'


def test_overlay_deleted_reference_clears_and_next_capture_opens(app, monkeypatch, config):
    from snapshot_pro import ScreenGrabber
    pixmap=QPixmap(640,480); pixmap.fill(QColor('white'))
    monkeypatch.setattr(ScreenGrabber,'grab_full_desktop', staticmethod(lambda: (pixmap,QRect(0,0,640,480))))
    controller=SnapShotController(); controller.config=config
    controller._do_launch_overlay()
    first=controller.active_overlay; first.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert controller.active_overlay is None
    controller._do_launch_overlay()
    assert controller.active_overlay is not None and controller.active_overlay is not first
    controller.active_overlay.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    controller.hotkey_manager.stop(); controller.deleteLater()


def test_ocr_job_does_not_block_ui_and_preserves_dialog(app, monkeypatch, config):
    def slow_ocr(image, language):
        time.sleep(.12)
        return 'Local text'
    monkeypatch.setattr('snapshot_pro.extract_text', slow_ocr)
    controller=SnapShotController(); controller.config=config
    image=QImage(80,60,QImage.Format.Format_RGB32)
    started=time.monotonic(); controller._run_ocr(image)
    assert time.monotonic()-started < .08
    deadline=time.monotonic()+3
    while controller._jobs and time.monotonic()<deadline:
        app.processEvents(); QTest.qWait(10)
    assert not controller._jobs
    assert app.clipboard().text() == 'Local text'
    assert len(controller._dialogs) == 1
    for dialog in list(controller._dialogs): dialog.close()
    controller.hotkey_manager.stop();controller.deleteLater()


def test_scroll_first_frame_uses_global_region_and_cancel_stops_timer(app, monkeypatch):
    targets=[]
    def grab(rect):
        targets.append(rect);pixmap=QPixmap(80,60);pixmap.fill(QColor('white'));return pixmap
    monkeypatch.setattr('snapshot_pro.ScreenGrabber.grab_region', staticmethod(grab))
    rect=QRect(-300,50,80,60)
    controller=ScrollingCaptureController(rect)
    QTest.qWait(450)
    assert targets == [rect]
    assert len(controller.captured_frames)==1
    controller.auto_check.setChecked(True)
    assert controller.timer.isActive()
    controller.cancel_capture()
    assert not controller.timer.isActive()


def test_pasted_image_editor_preserves_source_pixels(app, config):
    controller=SnapShotController();controller.config=config
    pixmap=QPixmap(100,60);pixmap.fill(QColor('#164273'))
    controller._open_editor(pixmap)
    overlay=controller.active_overlay
    assert overlay.editor_mode
    assert overlay.render_final_crop().toImage() == pixmap.toImage()
    overlay.close();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    controller.hotkey_manager.stop();controller.deleteLater()
