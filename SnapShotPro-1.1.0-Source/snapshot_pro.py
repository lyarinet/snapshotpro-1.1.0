#!/usr/bin/env python3
"""
SnapShot Pro — Ultra-Fast Cross-Platform Screenshot & Annotation Suite
Compatible with: Windows, macOS, and Linux
Features:
- Lightshot-Style Fast Region Capture & 9 Annotation Tools
- Multiple Consecutive Capture Mode (Multi-Snip with Auto-Stitch)
- [Feature 1] OCR Text Extraction (Copy text from any screenshot to clipboard)
- [Feature 2] Scrolling / Long Page Capture (Auto & manual vertical scroll stitching)
- [Feature 4] Smart Window Auto-Snap / Border Detection (Hover to detect and 1-click snap windows)
- System Tray Integration, Floating Magnifier Loupe, Pin to Screen, and Custom Hotkeys
"""

from __future__ import annotations

import ctypes
import datetime
import importlib.util
import math
import os
import pathlib
import platform
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple

if platform.system() == "Windows":
    try:
        import ctypes.wintypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "snapshotpro.screentool.app.1.0"
        )
    except Exception:
        pass


from PyQt6.QtCore import (  # noqa: E402
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    QLockFile,
    QStandardPaths,
    QThreadPool,
    QSize,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (  # noqa: E402
    QAction,
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QImageReader,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QGridLayout,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from snapshot_core import (
    VERSION, MAX_IMAGE_PIXELS, ImageJob, crop_pixmap, physical_rect,
    image_to_pil, pil_to_image, stitch_images, save_image, extract_text,
    save_gif,
)
from snapshot_native import GlobalHotkeyManager, scroll_down

# Capture and Pillow are loaded only when a user requests them.
HAS_MSS = importlib.util.find_spec("mss") is not None


def qpixmap_to_pil(pixmap):
    return image_to_pil(pixmap.toImage())


def pil_to_qpixmap(image):
    return QPixmap.fromImage(pil_to_image(image))


class OCRExtractor:
    @staticmethod
    def extract_text_from_pixmap(pixmap):
        try:
            return True, extract_text(pixmap.toImage())
        except Exception as error:
            return False, str(error)


class OCRResultDialog(QDialog):
    """Sleek dark-themed dialog displaying extracted OCR text with 1-click Copy."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SnapShot Pro — Extracted Text (OCR)")
        self.setMinimumSize(500, 340)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F172A;
                color: #F8FAFC;
            }
            QTextEdit {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
                font-family: monospace;
            }
            QPushButton {
                background-color: #4F46E5;
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6366F1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QLabel("Extracted text — edit or copy below")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #38BDF8;")
        layout.addWidget(header)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        layout.addWidget(self.text_edit)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy All Text")
        btn_copy.clicked.connect(self._copy_text)
        btn_row.addWidget(btn_copy)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #334155; color: #F8FAFC;")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _copy_text(self) -> None:
        QApplication.clipboard().setText(self.text_edit.toPlainText())


# ============================================================================
# 2. SMART WINDOW AUTO-SNAP & BORDER DETECTION (FEATURE 4)
# ============================================================================

class WindowDetector:
    """Enumerates open desktop windows for automatic snapping on mouse hover."""

    @staticmethod
    def get_visible_windows() -> List[Tuple[QRect, str]]:
        windows = []
        if platform.system() == "Windows":
            try:
                from ctypes import wintypes as wt
                user32 = ctypes.windll.user32
                user32.IsWindowVisible.argtypes = [wt.HWND]
                user32.IsIconic.argtypes = [wt.HWND]
                user32.GetWindowTextLengthW.argtypes = [wt.HWND]
                user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
                user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
                user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
                user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
                user32.MonitorFromWindow.restype = wt.HANDLE

                class MonitorInfo(ctypes.Structure):
                    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD),
                                ("szDevice", wt.WCHAR * 32)]

                user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MonitorInfo)]
                dwm = ctypes.windll.dwmapi
                dwm.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
                qt_screens = {screen.name().lower(): screen for screen in QGuiApplication.screens()}

                def enum_handler(hwnd, extra):
                    if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                        return 1
                    pid = wt.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == os.getpid():
                        return 1
                    cloaked = wt.DWORD()
                    dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                    if cloaked.value:
                        return 1
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length <= 0:
                        return 1
                    title_buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title_buffer, length + 1)
                    if title_buffer.value == "Program Manager":
                        return 1
                    rect = wt.RECT()
                    if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    if rect.right - rect.left < 50 or rect.bottom - rect.top < 50:
                        return 1
                    bounds = QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
                    monitor = MonitorInfo()
                    monitor.cbSize = ctypes.sizeof(monitor)
                    handle = user32.MonitorFromWindow(hwnd, 2)
                    if user32.GetMonitorInfoW(handle, ctypes.byref(monitor)):
                        screen = qt_screens.get(monitor.szDevice.lower())
                        if screen:
                            logical = screen.geometry()
                            native = monitor.rcMonitor
                            sx = logical.width() / max(1, native.right - native.left)
                            sy = logical.height() / max(1, native.bottom - native.top)
                            bounds = QRect(logical.left() + round((rect.left - native.left) * sx),
                                           logical.top() + round((rect.top - native.top) * sy),
                                           round(bounds.width() * sx), round(bounds.height() * sy))
                    windows.append((bounds, title_buffer.value))
                    return 1

                callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
                user32.EnumWindows.argtypes = [callback_type, wt.LPARAM]
                user32.EnumWindows.restype = wt.BOOL
                user32.EnumWindows(callback_type(enum_handler), 0)
            except Exception:
                pass

        if not windows:
            # Fallback for Linux/macOS or when ctypes is restricted
            screens = QGuiApplication.screens()
            for idx, s in enumerate(screens, start=1):
                windows.append((s.geometry(), f"Screen {idx}"))
        return windows


# ============================================================================
# 3. SCROLLING / LONG PAGE SCREENSHOT ENGINE (FEATURE 2)
# ============================================================================

class ScrollStitcher:
    @staticmethod
    def stitch_frames(frames):
        return QPixmap.fromImage(stitch_images([frame.toImage() for frame in frames]))


class ScrollingCaptureController(QWidget):
    """Bounded, cancellable manual/automatic capture of a global screen rectangle."""
    finished = pyqtSignal(list)
    cancelled = pyqtSignal()

    def __init__(self, target_rect, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.target_rect = target_rect
        self.captured_frames = []
        self._pending = False
        self._closed = False
        self._duplicates = 0
        self.setObjectName("ScrollBox")
        self.setStyleSheet("""
            QWidget#ScrollBox { background: #111c2d; border: 1px solid #29d6ba; border-radius: 10px; }
            QLabel, QCheckBox { color: #e2e8f0; font-size: 12px; }
            QPushButton { background: #23354c; color: white; border: 0; border-radius: 5px; padding: 8px; }
            QPushButton:hover { background: #34506d; }
        """)
        layout = QVBoxLayout(self)
        self.info_lbl = QLabel("Scroll capture • preparing first frame…")
        layout.addWidget(self.info_lbl)
        hint = QLabel("Select content only. Exclude fixed headers/footers.\nScroll down, then capture the next frame with some overlap.")
        layout.addWidget(hint)
        row = QHBoxLayout()
        self.btn_capture = QPushButton("Capture frame")
        self.btn_capture.clicked.connect(self.capture_current_frame)
        row.addWidget(self.btn_capture)
        self.btn_finish = QPushButton("Finish & stitch")
        self.btn_finish.clicked.connect(self.finish_capture)
        row.addWidget(self.btn_finish)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancel_capture)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.auto_check = QCheckBox("Auto-scroll (stops when the page stops changing)")
        self.auto_check.toggled.connect(self._auto_changed)
        layout.addWidget(self.auto_check)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._auto_tick)
        self.adjustSize()
        screen = QGuiApplication.screenAt(target_rect.center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        self.move(max(available.left(), min(target_rect.right() + 12, available.right() - self.width())),
                  max(available.top(), min(target_rect.top(), available.bottom() - self.height())))
        QTimer.singleShot(220, self.capture_current_frame)

    def _auto_changed(self, enabled):
        if enabled:
            self.timer.start()
        else:
            self.timer.stop()

    def _auto_tick(self):
        if self._pending or self._closed:
            return
        try:
            center = self.target_rect.center()
            scroll_down(center.x(), center.y())
        except Exception as error:
            self.auto_check.setChecked(False)
            self.info_lbl.setText(f"Auto-scroll unavailable. Use manual frames. {str(error)[:80]}")
            return
        QTimer.singleShot(450, self.capture_current_frame)

    def capture_current_frame(self):
        if self._closed or self._pending:
            return
        self._pending = True
        self.btn_finish.setEnabled(False)
        self.hide()
        QTimer.singleShot(160, self._grab_and_show)

    def _grab_and_show(self):
        if self._closed:
            return
        try:
            cropped = ScreenGrabber.grab_region(self.target_rect)
            if cropped.isNull():
                raise RuntimeError("Screen capture failed. Check screen-recording permission.")
            duplicate = bool(self.captured_frames and
                             cropped.toImage() == self.captured_frames[-1].toImage())
            if duplicate:
                self._duplicates += 1
            else:
                pixels = sum(p.width() * p.height() for p in self.captured_frames)
                if pixels + cropped.width() * cropped.height() > MAX_IMAGE_PIXELS:
                    self.auto_check.setChecked(False)
                    raise RuntimeError("48 megapixel limit reached. Finish this capture.")
                self._duplicates = 0
                self.captured_frames.append(cropped)
            self.info_lbl.setText(f"Scroll capture • {len(self.captured_frames)} frames" +
                                  (" • unchanged frame skipped" if duplicate else ""))
            if self._duplicates >= 2:
                self.auto_check.setChecked(False)
                self.info_lbl.setText("Page unchanged • press Finish & stitch")
        except Exception as error:
            self.auto_check.setChecked(False)
            self.info_lbl.setText(str(error))
        finally:
            self._pending = False
            self.btn_finish.setEnabled(bool(self.captured_frames))
            self.show()

    def finish_capture(self):
        if self._pending or not self.captured_frames:
            return
        self._closed = True
        self.timer.stop()
        self.finished.emit(self.captured_frames)
        self.close()

    def cancel_capture(self):
        self._closed = True
        self.timer.stop()
        self.cancelled.emit()
        self.close()

    def closeEvent(self, event):
        self.timer.stop()
        if not self._closed:
            self._closed = True
            self.cancelled.emit()
        event.accept()


class RecordingBorderOverlay(QWidget):
    """Visual dashed red border highlighting the exact screen area being recorded."""

    def __init__(self, target_rect: QRect):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                               Qt.WindowType.WindowStaysOnTopHint |
                               Qt.WindowType.Tool |
                               Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        margin = 3
        self.setGeometry(target_rect.adjusted(-margin, -margin, margin, margin))

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor("#EF4444"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)


class ScreenRecorderController(QWidget):
    """Floating controller for recording a screen region into an animated GIF."""
    finished = pyqtSignal(list)
    cancelled = pyqtSignal()

    def __init__(self, target_rect: QRect, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.target_rect = target_rect
        self.captured_frames: List[QPixmap] = []
        self._recording = False
        self._closed = False
        self.max_duration_seconds = 60
        self.elapsed_ms = 0

        self.setObjectName("RecBox")
        self.setStyleSheet("""
            QWidget#RecBox { background: #0f172a; border: 2px solid #ef4444; border-radius: 10px; }
            QLabel { color: #f8fafc; font-size: 12px; }
            QPushButton { background: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 6px; padding: 6px 12px; font-weight: 600; font-size: 12px; }
            QPushButton:hover { background: #334155; }
            QPushButton#StopBtn { background: #ef4444; border-color: #dc2626; color: #ffffff; }
            QPushButton#StopBtn:hover { background: #dc2626; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.rec_lbl = QLabel("🔴 REC")
        self.rec_lbl.setStyleSheet("color: #ef4444; font-weight: 800; font-size: 13px;")
        layout.addWidget(self.rec_lbl)

        self.time_lbl = QLabel("00:00")
        self.time_lbl.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 13px; font-family: monospace;")
        layout.addWidget(self.time_lbl)

        self.frame_lbl = QLabel("0 frames")
        self.frame_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.frame_lbl)

        layout.addSpacing(6)

        self.stop_btn = QPushButton("⏹ Stop && Save GIF")
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.clicked.connect(self.finish_recording)
        layout.addWidget(self.stop_btn)

        cancel_btn = QPushButton("✕ Cancel")
        cancel_btn.clicked.connect(self.cancel_recording)
        layout.addWidget(cancel_btn)

        self.adjustSize()

        # Position controller smartly near target_rect
        screen = QGuiApplication.screenAt(target_rect.center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = max(avail.left(), min(target_rect.center().x() - self.width() // 2, avail.right() - self.width()))
        if target_rect.bottom() + self.height() + 15 <= avail.bottom():
            y = target_rect.bottom() + 10
        elif target_rect.top() - self.height() - 15 >= avail.top():
            y = target_rect.top() - self.height() - 10
        else:
            y = avail.top() + 10
        self.move(x, y)

        # Pulse animation for REC text
        self._pulse_state = True
        self.pulse_timer = QTimer(self)
        self.pulse_timer.setInterval(600)
        self.pulse_timer.timeout.connect(self._pulse_tick)
        self.pulse_timer.start()

        # Recording timer (100ms = 10 FPS)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._record_tick)

        # Visual indicator border around recording area
        self.border_overlay = RecordingBorderOverlay(target_rect)
        self.border_overlay.show()

        QTimer.singleShot(250, self.start_recording)

    def _pulse_tick(self):
        self._pulse_state = not self._pulse_state
        color = "#ef4444" if self._pulse_state else "#64748b"
        self.rec_lbl.setStyleSheet(f"color: {color}; font-weight: 800; font-size: 13px;")

    def start_recording(self):
        if self._closed:
            return
        self._recording = True
        self.timer.start()

    def _record_tick(self):
        if self._closed or not self._recording:
            return
        self.elapsed_ms += self.timer.interval()
        total_seconds = self.elapsed_ms // 1000
        mins = total_seconds // 60
        secs = total_seconds % 60
        self.time_lbl.setText(f"{mins:02d}:{secs:02d}")

        try:
            pix = ScreenGrabber.grab_region(self.target_rect)
            if not pix.isNull():
                self.captured_frames.append(pix)
                self.frame_lbl.setText(f"{len(self.captured_frames)} frames")
        except Exception:
            pass

        if total_seconds >= self.max_duration_seconds:
            self.finish_recording()

    def finish_recording(self):
        if self._closed or not self.captured_frames:
            self.cancel_recording()
            return
        self._closed = True
        self.timer.stop()
        self.pulse_timer.stop()
        if hasattr(self, 'border_overlay') and self.border_overlay:
            self.border_overlay.close()
        self.finished.emit(self.captured_frames)
        self.close()

    def cancel_recording(self):
        self._closed = True
        self.timer.stop()
        self.pulse_timer.stop()
        if hasattr(self, 'border_overlay') and self.border_overlay:
            self.border_overlay.close()
        self.cancelled.emit()
        self.close()

    def closeEvent(self, event):
        self._closed = True
        self.timer.stop()
        self.pulse_timer.stop()
        if hasattr(self, 'border_overlay') and self.border_overlay:
            self.border_overlay.close()
        event.accept()



# ============================================================================
# 4. CONFIGURATION & SETTINGS MANAGER
# ============================================================================

class AppConfig:
    """Manages persistent cross-platform user settings via QSettings."""

    def __init__(self) -> None:
        self.settings = QSettings("SnapShotPro", "SnapShotProApp")

    @property
    def hotkey_region(self) -> str:
        return str(self.settings.value("hotkey_region", "Print"))

    @hotkey_region.setter
    def hotkey_region(self, value: str) -> None:
        self.settings.setValue("hotkey_region", value.strip() or "Print")

    @property
    def hotkey_secondary(self) -> str:
        return str(self.settings.value("hotkey_secondary", "Ctrl+Shift+S"))

    @hotkey_secondary.setter
    def hotkey_secondary(self, value: str) -> None:
        self.settings.setValue("hotkey_secondary", value.strip() or "Ctrl+Shift+S")

    @property
    def hotkey_fullscreen(self) -> str:
        return str(self.settings.value("hotkey_fullscreen", "Ctrl+Shift+F"))

    @hotkey_fullscreen.setter
    def hotkey_fullscreen(self, value: str) -> None:
        self.settings.setValue("hotkey_fullscreen", value.strip() or "Ctrl+Shift+F")

    @property
    def hotkey_multicapture(self) -> str:
        return str(self.settings.value("hotkey_multicapture", "Ctrl+Shift+M"))

    @hotkey_multicapture.setter
    def hotkey_multicapture(self, value: str) -> None:
        self.settings.setValue("hotkey_multicapture", value.strip() or "Ctrl+Shift+M")

    @property
    def auto_copy_clipboard(self) -> bool:
        return self.settings.value("auto_copy_clipboard", False, type=bool)

    @auto_copy_clipboard.setter
    def auto_copy_clipboard(self, value: bool) -> None:
        self.settings.setValue("auto_copy_clipboard", bool(value))

    @property
    def show_magnifier(self) -> bool:
        return self.settings.value("show_magnifier", True, type=bool)

    @show_magnifier.setter
    def show_magnifier(self, value: bool) -> None:
        self.settings.setValue("show_magnifier", bool(value))

    @property
    def auto_snap_windows(self) -> bool:
        return self.settings.value("auto_snap_windows", False, type=bool)

    @auto_snap_windows.setter
    def auto_snap_windows(self, value: bool) -> None:
        self.settings.setValue("auto_snap_windows", bool(value))

    @property
    def image_format(self) -> str:
        value = str(self.settings.value("image_format", "PNG")).upper()
        return value if value in {"PNG", "JPG", "WEBP"} else "PNG"

    @image_format.setter
    def image_format(self, value: str) -> None:
        self.settings.setValue("image_format", value.upper())

    @property
    def save_directory(self) -> str:
        default_dir = str(pathlib.Path.home() / "Pictures" / "SnapShotPro")
        return str(self.settings.value("save_directory", default_dir)).strip() or default_dir

    @save_directory.setter
    def save_directory(self, value: str) -> None:
        self.settings.setValue("save_directory", value)

    @property
    def ocr_language(self):
        return str(self.settings.value("ocr_language", "eng")).strip() or "eng"

    @ocr_language.setter
    def ocr_language(self, value):
        self.settings.setValue("ocr_language", value.strip() or "eng")

    @property
    def autostart_enabled(self) -> bool:
        if platform.system() != "Windows":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, "SnapShot Pro")
                return bool(val)
        except Exception:
            return False

    @autostart_enabled.setter
    def autostart_enabled(self, enable: bool) -> None:
        if platform.system() != "Windows":
            return
        try:
            import winreg
            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            if enable:
                exe_path = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "SnapShot Pro", 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, "SnapShot Pro")
                except FileNotFoundError:
                    pass
        except Exception:
            pass

    def reset_defaults(self) -> None:
        self.settings.clear()


# ============================================================================
# 5. DYNAMIC ICON GENERATOR
# ============================================================================

def create_app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg_rect = QRectF(4, 4, 56, 56)
    path = QPainterPath()
    path.addRoundedRect(bg_rect, 14, 14)
    painter.fillPath(path, QColor("#6366F1"))

    pen = QPen(QColor("#FFFFFF"), 3.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawRect(QRectF(16, 16, 32, 32))

    painter.setBrush(QColor("#38BDF8"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(32, 32), 7, 7)

    painter.end()
    return QIcon(pixmap)


def get_app_icon() -> QIcon:
    """Returns application QIcon from bundled assets or falls back to procedural icon."""
    base_dir = getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent)
    base_path = pathlib.Path(base_dir)
    for rel in ("assets/icon.ico", "assets/icon.png", "icon.ico", "icon.png"):
        candidate = base_path / rel
        if candidate.exists():
            return QIcon(str(candidate))
    return create_app_icon()


# ============================================================================
# 6. ULTRA-FAST CROSS-PLATFORM SCREEN CAPTURE ENGINE
# ============================================================================

class ScreenGrabber:
    @staticmethod
    def grab_full_desktop():
        screens = QGuiApplication.screens()
        if not screens:
            return QPixmap(), QRect()
        virtual = screens[0].geometry()
        for screen in screens[1:]:
            virtual = virtual.united(screen.geometry())
        scale = max(screen.devicePixelRatio() for screen in screens)
        # MSS is fastest when native and Qt coordinates are the same.
        if HAS_MSS and all(screen.devicePixelRatio() == 1 for screen in screens):
            try:
                import mss
                with mss.mss() as capture:
                    monitor = capture.monitors[0]
                    rect = QRect(monitor["left"], monitor["top"], monitor["width"], monitor["height"])
                    if rect == virtual:
                        raw = capture.grab(monitor)
                        image = QImage(raw.bgra, raw.width, raw.height, raw.width * 4,
                                       QImage.Format.Format_ARGB32).copy()
                        return QPixmap.fromImage(image), virtual
            except Exception:
                pass
        # Per-monitor Qt capture preserves Retina/mixed-DPI content and negative origins.
        canvas = QPixmap(round(virtual.width() * scale), round(virtual.height() * scale))
        canvas.setDevicePixelRatio(scale)
        canvas.fill(Qt.GlobalColor.black)
        painter = QPainter(canvas)
        found = False
        for screen in screens:
            shot = screen.grabWindow(0)
            if not shot.isNull():
                painter.drawPixmap(QRectF(screen.geometry().translated(-virtual.topLeft())),
                                   shot, QRectF(shot.rect()))
                found = True
        painter.end()
        return (canvas if found else QPixmap()), virtual

    @staticmethod
    def grab_region(global_rect):
        desktop, virtual = ScreenGrabber.grab_full_desktop()
        if desktop.isNull():
            return QPixmap()
        local = global_rect.intersected(virtual).translated(-virtual.topLeft())
        return crop_pixmap(desktop, local)

    @staticmethod
    def grab_each_monitor():
        return [(screen.grabWindow(0), f"Monitor_{index}")
                for index, screen in enumerate(QGuiApplication.screens(), 1)]


# ============================================================================
# 7. GLOBAL HOTKEY BRIDGE
# ============================================================================

# ============================================================================
# 8. FLOATING PINNED SCREENSHOT WINDOW
# ============================================================================

class PinnedScreenshotWindow(QWidget):
    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.original_pixmap = pixmap
        self.scale_factor = 1.0
        self._drag_pos: Optional[QPoint] = None

        self.resize(pixmap.deviceIndependentSize().toSize() + QSize(8, 8))
        self.setToolTip("Drag to move • Scroll to zoom • Double-click or Esc to close")

    def _reset_zoom(self):
        self.scale_factor = 1.0
        self.resize(self.original_pixmap.deviceIndependentSize().toSize() + QSize(8, 8))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#1E293B"))

        target_rect = self.rect().adjusted(4, 4, -4, -4)
        painter.drawPixmap(target_rect, self.original_pixmap)

        pen = QPen(QColor("#38BDF8"), 2)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.addAction("Copy image", lambda: QApplication.clipboard().setPixmap(self.original_pixmap))
            menu.addAction("Reset zoom", self._reset_zoom)
            opacity = menu.addMenu("Opacity")
            for percent in (100, 80, 60, 40):
                opacity.addAction(f"{percent}%", lambda checked=False, p=percent: self.setWindowOpacity(p / 100))
            menu.addAction("Close", self.close)
            menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        self.close()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        self.scale_factor = min(3.0, self.scale_factor * 1.1) if delta > 0 else max(0.25, self.scale_factor * 0.9)
        new_w = int(self.original_pixmap.deviceIndependentSize().width() * self.scale_factor) + 8
        new_h = int(self.original_pixmap.deviceIndependentSize().height() * self.scale_factor) + 8
        self.resize(new_w, new_h)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()


# ============================================================================
# 9. ANNOTATION DATA MODEL
# ============================================================================

class ToolType(Enum):
    SELECT_MOVE = auto()
    PEN = auto()
    LINE = auto()
    ARROW = auto()
    RECTANGLE = auto()
    ELLIPSE = auto()
    HIGHLIGHTER = auto()
    TEXT = auto()
    STEP_COUNTER = auto()
    PIXELATE = auto()
    REDACT = auto()


@dataclass
class AnnotationItem:
    tool: ToolType
    color: QColor
    thickness: int
    start: QPoint = field(default_factory=QPoint)
    end: QPoint = field(default_factory=QPoint)
    points: List[QPoint] = field(default_factory=list)
    text: str = ""
    step_number: int = 1


# ============================================================================
# 10. LIGHTSHOT OVERLAY WITH SMART SNAP, OCR & MULTI-CAPTURE
# ============================================================================

class CaptureOverlay(QWidget):
    """
    Overlay featuring:
    - Smart Window Auto-Snap on hover (Feature 4)
    - OCR Text Extraction (Feature 1)
    - Scrolling Screenshot Launcher (Feature 2)
    - Multiple Consecutive Snips (Multi-Capture)
    - 9 Vector Annotation Tools
    """

    pinned_created = pyqtSignal(object)
    notification_requested = pyqtSignal(str, str)
    multicapture_finished = pyqtSignal(list)
    scroll_capture_requested = pyqtSignal(QRect)
    ocr_requested = pyqtSignal(QImage)
    gif_record_requested = pyqtSignal(QRect)

    HANDLE_SIZE = 8

    def __init__(
        self,
        desktop_pixmap: QPixmap,
        virtual_rect: QRect,
        config: AppConfig,
        multi_mode: bool = False,
        ocr_mode: bool = False,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.desktop_pixmap = desktop_pixmap
        self.working_pixmap = desktop_pixmap  # implicit sharing; no second desktop allocation
        self._sample_image = desktop_pixmap.toImage()
        self.scroll_mode = False
        self.gif_mode = False
        self.editor_mode = False
        self.virtual_rect = virtual_rect
        self.config = config
        self.multi_mode = multi_mode
        self.ocr_mode = ocr_mode

        self.captured_crops: List[QPixmap] = []

        # Smart Window Auto-Snap cache
        self.detected_windows: List[Tuple[QRect, str]] = []
        self.hovered_window: Optional[Tuple[QRect, str]] = None
        self.potential_snap_window: Optional[Tuple[QRect, str]] = None
        if self.config.auto_snap_windows:
            raw_wins = WindowDetector.get_visible_windows()
            origin = virtual_rect.topLeft()
            self.detected_windows = [
                (w_rect.translated(-origin), title)
                for w_rect, title in raw_wins
            ]

        self.setGeometry(virtual_rect)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.selection_rect = QRect()
        self.is_selecting = False
        self.is_moving_selection = False
        self.active_resize_handle: Optional[str] = None
        self.drag_origin = QPoint()
        self.rect_at_drag_start = QRect()
        self.current_mouse_pos = QPoint()

        self.current_tool: ToolType = ToolType.SELECT_MOVE
        self.current_color = QColor("#EF4444")
        self.current_thickness = 4
        self.step_counter_value = 1

        self.annotations: List[AnnotationItem] = []
        self.redo_stack: List[AnnotationItem] = []
        self.active_annotation: Optional[AnnotationItem] = None

        self._build_floating_toolbars()

    def _build_floating_toolbars(self) -> None:
        toolbar_style = """
            QWidget#FloatingBar {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 5px;
                padding: 5px 9px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #64748B;
            }
            QPushButton:checked {
                background-color: #4F46E5;
                border-color: #818CF8;
                color: #FFFFFF;
            }
            QLabel {
                color: #CBD5E1;
                font-size: 11px;
                font-weight: 600;
            }
        """

        # 1. Tools Bar
        self.tools_bar = QWidget(self)
        self.tools_bar.setObjectName("FloatingBar")
        self.tools_bar.setStyleSheet(toolbar_style)
        tools_layout = QGridLayout(self.tools_bar)
        tools_layout.setContentsMargins(6, 6, 6, 6)
        tools_layout.setSpacing(4)

        self.tool_buttons = {}
        tool_specs = [
            (ToolType.SELECT_MOVE, "↔", "Move/Resize Selection (M)"),
            (ToolType.PEN, "✎", "Freehand Pen (P)"),
            (ToolType.LINE, "╱", "Straight Line (L)"),
            (ToolType.ARROW, "➤", "Arrow Pointer (A)"),
            (ToolType.RECTANGLE, "□", "Rectangle Box (R)"),
            (ToolType.ELLIPSE, "○", "Ellipse / Circle (E)"),
            (ToolType.HIGHLIGHTER, "▰", "Highlighter Marker (H)"),
            (ToolType.TEXT, "T", "Add Text Label (T)"),
            (ToolType.STEP_COUNTER, "①", "Numbered Step Callout (N)"),
            (ToolType.PIXELATE, "▦", "Pixelate (B)"),
            (ToolType.REDACT, "■", "Solid redaction / cover (K)"),
        ]

        for index, (t_type, label, tip) in enumerate(tool_specs):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda checked, tt=t_type: self.select_tool(tt))
            btn.setFixedSize(36, 32)
            tools_layout.addWidget(btn, index // 6, index % 6)
            self.tool_buttons[t_type] = btn

        self.tool_buttons[ToolType.SELECT_MOVE].setChecked(True)

        self.color_btn = QPushButton("Color")
        self.color_btn.setToolTip("Choose Annotation Color")
        self._update_color_btn_style()
        self.color_btn.clicked.connect(self.choose_color)
        tools_layout.addWidget(self.color_btn, 2, 0, 1, 2)

        size_lbl = QLabel("Size:")
        tools_layout.addWidget(size_lbl, 2, 2)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(2, 20)
        self.size_slider.setValue(self.current_thickness)
        self.size_slider.setFixedWidth(65)
        self.size_slider.valueChanged.connect(self._on_thickness_changed)
        tools_layout.addWidget(self.size_slider, 2, 3, 1, 3)

        self.tools_bar.adjustSize()
        self.tools_bar.hide()

        # 2. Actions Bar (with OCR, Scroll Capture, Multi-Snip, Pin, Save, Copy)
        self.actions_bar = QWidget(self)
        self.actions_bar.setObjectName("FloatingBar")
        self.actions_bar.setStyleSheet(toolbar_style)
        act_layout = QGridLayout(self.actions_bar)
        act_layout.setContentsMargins(6, 6, 6, 6)
        act_layout.setSpacing(4)

        # Multi-Snip Toggle
        self.multi_btn = QPushButton("🔁 Multi-Snip")
        self.multi_btn.setCheckable(True)
        self.multi_btn.setChecked(self.multi_mode)
        self._update_multi_btn_style()
        self.multi_btn.clicked.connect(self._toggle_multi_mode)
        act_layout.addWidget(self.multi_btn, 0, 0)

        # [FEATURE 1] OCR Text Extraction Button
        btn_ocr = QPushButton("OCR Text")
        btn_ocr.setToolTip("Extract and copy text from screenshot (Ctrl+T)")
        btn_ocr.setStyleSheet("background-color: #7C3AED; color: white;")
        btn_ocr.clicked.connect(self.action_extract_ocr_text)
        act_layout.addWidget(btn_ocr, 0, 1)

        # [FEATURE 2] Scrolling Capture Button
        btn_scroll = QPushButton("Scroll")
        self.scroll_btn = btn_scroll
        btn_scroll.setToolTip("Start Scrolling Long Screenshot of this area")
        btn_scroll.setStyleSheet("background-color: #0D9488; color: white;")
        btn_scroll.clicked.connect(self.action_start_scroll_capture)
        act_layout.addWidget(btn_scroll, 0, 2)

        # [FEATURE 5] GIF Recorder Button
        btn_gif = QPushButton("🎥 GIF")
        btn_gif.setToolTip("Record selected region as animated GIF")
        btn_gif.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold;")
        btn_gif.clicked.connect(self.action_start_gif_recording)
        act_layout.addWidget(btn_gif, 0, 3)

        undo_btn = QPushButton("Undo")
        undo_btn.setToolTip("Undo Last Annotation (Ctrl+Z)")
        undo_btn.clicked.connect(self.undo_annotation)
        act_layout.addWidget(undo_btn, 1, 0)

        redo_btn = QPushButton("Redo")
        redo_btn.setToolTip("Redo Annotation (Ctrl+Y)")
        redo_btn.clicked.connect(self.redo_annotation)
        act_layout.addWidget(redo_btn, 1, 1)

        pin_btn = QPushButton("Pin")
        pin_btn.setToolTip("Float Screenshot on Top (Ctrl+P)")
        pin_btn.setStyleSheet("background-color: #0284C7; color: white;")
        pin_btn.clicked.connect(self.action_pin_to_screen)
        act_layout.addWidget(pin_btn, 1, 2)

        quick_save_btn = QPushButton("Save")
        quick_save_btn.setToolTip("Instant Save (Ctrl+D)")
        quick_save_btn.clicked.connect(self.action_quick_save)
        act_layout.addWidget(quick_save_btn, 1, 3)

        copy_btn = QPushButton("Copy (Enter)")
        copy_btn.setStyleSheet("background-color: #4F46E5; color: white;")
        copy_btn.clicked.connect(self.action_copy_clipboard)
        act_layout.addWidget(copy_btn, 2, 0, 1, 2)

        self.finish_btn = QPushButton("Finish (Esc)")
        self.finish_btn.setStyleSheet("background-color: #334155; color: white;")
        self.finish_btn.clicked.connect(self.finish_and_close)
        act_layout.addWidget(self.finish_btn, 2, 2, 1, 2)

        self.actions_bar.adjustSize()
        self.actions_bar.hide()

    def _update_color_btn_style(self) -> None:
        hex_c = self.current_color.name()
        self.color_btn.setStyleSheet(
            f"background-color: {hex_c}; color: #FFFFFF; border: 2px solid #F8FAFC; border-radius: 5px; padding: 5px 10px;"
        )

    def _update_multi_btn_style(self) -> None:
        if self.multi_mode:
            count = len(self.captured_crops)
            self.multi_btn.setText(f"🔁 Multi ({count})")
            self.multi_btn.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        else:
            self.multi_btn.setText("Multi-Snip")
            self.multi_btn.setStyleSheet("background-color: #1E293B; color: #94A3B8;")

    def _toggle_multi_mode(self, checked=None) -> None:
        self.multi_mode = (not self.multi_mode) if checked is None else checked
        self.multi_btn.setChecked(self.multi_mode)
        self._update_multi_btn_style()

    def _on_thickness_changed(self, value: int) -> None:
        self.current_thickness = value

    def select_tool(self, tool: ToolType) -> None:
        self.current_tool = tool
        for tt, btn in self.tool_buttons.items():
            btn.setChecked(tt == tool)
        self.setCursor(Qt.CursorShape.SizeAllCursor if tool == ToolType.SELECT_MOVE else Qt.CursorShape.CrossCursor)

    def choose_color(self) -> None:
        color = QColorDialog.getColor(self.current_color, self, "Choose Annotation Color")
        if color.isValid():
            self.current_color = color
            self._update_color_btn_style()

    def _position_toolbars(self):
        sel = self.selection_rect.normalized()
        if sel.width() < 6 or sel.height() < 6:
            self.tools_bar.hide()
            self.actions_bar.hide()
            return
        self.tools_bar.adjustSize()
        self.actions_bar.adjustSize()
        screen = QGuiApplication.screenAt(self.virtual_rect.topLeft() + sel.center())
        bounds = self.rect()
        if screen and not self.editor_mode:
            bounds = screen.geometry().translated(-self.virtual_rect.topLeft()).intersected(bounds)
        tw, th = self.tools_bar.width(), self.tools_bar.height()
        aw, ah = self.actions_bar.width(), self.actions_bar.height()
        # Prefer side-by-side below the crop; use an inside edge for full-screen crops.
        left = max(bounds.left() + 4, min(sel.left(), bounds.right() - tw - aw - 14))
        top = sel.bottom() + 10
        if top + max(th, ah) > bounds.bottom() - 4:
            top = sel.top() - max(th, ah) - 10
        top = max(bounds.top() + 4, min(top, bounds.bottom() - max(th, ah) - 4))
        if tw + aw + 20 <= bounds.width():
            self.tools_bar.move(left, top)
            self.actions_bar.move(left + tw + 8, top)
        else:
            self.tools_bar.move(max(bounds.left() + 4, bounds.right() - tw - 4),
                                max(bounds.top() + 4, top - th - 6))
            self.actions_bar.move(max(bounds.left() + 4, bounds.right() - aw - 4), top)
        self.tools_bar.show()
        self.actions_bar.show()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.drawPixmap(0, 0, self.working_pixmap)

        overlay_path = QPainterPath()
        overlay_path.addRect(QRectF(self.rect()))
        sel = self.selection_rect.normalized()

        if not sel.isNull() and sel.width() > 1 and sel.height() > 1:
            sel_path = QPainterPath()
            sel_path.addRect(QRectF(sel))
            overlay_path = overlay_path.subtracted(sel_path)

        painter.fillPath(overlay_path, QColor(0, 0, 0, 135))

        # [FEATURE 4] Draw Smart Window Auto-Snap Highlight on Hover
        if sel.isNull() and self.hovered_window is not None:
            w_rect, w_title = self.hovered_window
            snap_pen = QPen(QColor("#06B6D4"), 2.2, Qt.PenStyle.DashLine)
            painter.setPen(snap_pen)
            painter.setBrush(QColor(6, 182, 212, 35))
            painter.drawRect(w_rect)

            # Snap badge
            badge_text = f" 🪟 Snap Window: {w_title[:32]} ({w_rect.width()}×{w_rect.height()} px) - Click to Select "
            painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(15, 23, 42, 230))
            fm = painter.fontMetrics()
            bw = fm.horizontalAdvance(badge_text) + 12
            bh = fm.height() + 8
            b_rect = QRect(w_rect.left() + 10, max(10, w_rect.top() + 10), bw, bh)
            painter.drawRoundedRect(b_rect, 5, 5)
            painter.setPen(QColor("#38BDF8"))
            painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Preview uses the same clipping as the exported crop.
        painter.save()
        painter.setClipRect(sel)
        for item in self.annotations:
            self._draw_annotation(painter, item)
        if self.active_annotation is not None:
            self._draw_annotation(painter, self.active_annotation)

        painter.restore()

        # Selection rectangle & handles
        if not sel.isNull() and sel.width() > 1 and sel.height() > 1:
            pen = QPen(QColor("#38BDF8"), 1.8, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel)

            painter.setBrush(QColor("#FFFFFF"))
            painter.setPen(QPen(QColor("#0284C7"), 1.5))
            for _, h_rect in self._get_handle_rects(sel).items():
                painter.drawRect(h_rect)

            multi_tag = f" [Multi #{len(self.captured_crops)+1}]" if self.multi_mode else ""
            size = physical_rect(sel, self.working_pixmap.devicePixelRatio()).size()
            dim_text = f" {size.width()} × {size.height()} px{multi_tag} "
            font = QFont("Sans Serif", 9, QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(dim_text) + 12
            th = fm.height() + 8
            badge_y = sel.top() - th - 6 if sel.top() > th + 10 else sel.top() + 6
            badge_rect = QRect(sel.left(), badge_y, tw, th)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(15, 23, 42, 220))
            painter.drawRoundedRect(badge_rect, 5, 5)
            painter.setPen(QColor("#F8FAFC"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, dim_text)
        elif self.hovered_window is None:
            self._draw_initial_banner(painter)

        if self.config.show_magnifier and (self.is_selecting or sel.isNull()):
            self._draw_magnifier(painter, self.current_mouse_pos)

    def _draw_initial_banner(self, painter: QPainter) -> None:
        if self.ocr_mode:
            banner_text = "📝 OCR Mode: Drag mouse over any text to extract & copy  •  [Esc] Exit"
        elif self.config.auto_snap_windows:
            banner_text = "Drag with mouse to select custom area  •  Click to snap window  •  [C] Copy Color  •  [Esc] Exit"
        else:
            banner_text = "Drag with mouse to select any custom screen area  •  [C] Copy Color  •  [Esc] Exit"
        font = QFont("Sans Serif", 11, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(banner_text) + 36
        h = 40
        rect = QRect((self.width() - w) // 2, 28, w, h)
        painter.setPen(QPen(QColor("#38BDF8"), 1.5))
        painter.setBrush(QColor(15, 23, 42, 230))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, banner_text)

    def _draw_magnifier(self, painter: QPainter, pos: QPoint) -> None:
        if pos.isNull():
            return
        loupe_size = 116
        capture_radius = 14
        lx = pos.x() + 24
        ly = pos.y() + 24
        if lx + loupe_size + 10 > self.width():
            lx = pos.x() - loupe_size - 24
        if ly + loupe_size + 52 > self.height():
            ly = pos.y() - loupe_size - 60

        src_rect = QRect(
            pos.x() - capture_radius,
            pos.y() - capture_radius,
            capture_radius * 2,
            capture_radius * 2,
        )
        cropped = crop_pixmap(self.working_pixmap, src_rect)

        loupe_rect = QRect(lx, ly, loupe_size, loupe_size)
        painter.save()
        painter.setPen(QPen(QColor("#38BDF8"), 2))
        painter.setBrush(QColor("#0F172A"))
        painter.drawRoundedRect(QRect(lx - 2, ly - 2, loupe_size + 4, loupe_size + 48), 8, 8)

        painter.drawPixmap(loupe_rect, cropped)

        cx = lx + loupe_size // 2
        cy = ly + loupe_size // 2
        painter.setPen(QPen(QColor(56, 189, 248, 200), 1))
        painter.drawLine(lx, cy, lx + loupe_size, cy)
        painter.drawLine(cx, ly, cx, ly + loupe_size)

        img = self._sample_image
        hex_code = "#000000"
        sample = QPoint(round(pos.x() * self.working_pixmap.devicePixelRatio()),
                        round(pos.y() * self.working_pixmap.devicePixelRatio()))
        if img.rect().contains(sample):
            c = img.pixelColor(sample)
            hex_code = c.name().upper()
            painter.setBrush(c)
            painter.setPen(QPen(QColor("#FFFFFF"), 1))
            painter.drawRect(lx + 8, ly + loupe_size + 8, 16, 16)

        painter.setFont(QFont("Monospace", 8, QFont.Weight.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(lx + 30, ly + loupe_size + 20, f"{hex_code} ({pos.x()},{pos.y()})")
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(lx + 8, ly + loupe_size + 38, "Press [C] to copy HEX")
        painter.restore()

    def _draw_annotation(self, painter: QPainter, item: AnnotationItem) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if item.tool == ToolType.PEN:
            pen = QPen(item.color, item.thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for i in range(1, len(item.points)):
                painter.drawLine(item.points[i - 1], item.points[i])

        elif item.tool == ToolType.HIGHLIGHTER:
            hl_color = QColor(item.color)
            hl_color.setAlpha(95)
            pen = QPen(hl_color, max(14, item.thickness * 4), Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for i in range(1, len(item.points)):
                painter.drawLine(item.points[i - 1], item.points[i])

        elif item.tool == ToolType.LINE:
            pen = QPen(item.color, item.thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(item.start, item.end)

        elif item.tool == ToolType.ARROW:
            self._draw_arrow(painter, item.start, item.end, item.color, item.thickness)

        elif item.tool == ToolType.RECTANGLE:
            pen = QPen(item.color, item.thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(item.start, item.end).normalized())

        elif item.tool == ToolType.ELLIPSE:
            pen = QPen(item.color, item.thickness, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRect(item.start, item.end).normalized())

        elif item.tool == ToolType.TEXT and item.text:
            font = QFont("Sans Serif", max(11, item.thickness * 3 + 4), QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(item.text).adjusted(-6, -4, 6, 4)
            text_rect.moveTopLeft(item.start)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(15, 23, 42, 180))
            painter.drawRoundedRect(text_rect, 4, 4)
            painter.setPen(item.color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, item.text)

        elif item.tool == ToolType.STEP_COUNTER:
            radius = max(13, item.thickness * 2 + 8)
            center = item.start
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.setBrush(item.color)
            painter.drawEllipse(center, radius, radius)
            font = QFont("Sans Serif", max(10, radius - 4), QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF"))
            num_rect = QRect(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
            painter.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, str(item.step_number))

        elif item.tool == ToolType.REDACT:
            painter.fillRect(QRect(item.start, item.end).normalized(), item.color)

        elif item.tool == ToolType.PIXELATE:
            rect = QRect(item.start, item.end).normalized()
            if rect.width() > 4 and rect.height() > 4:
                self._draw_pixelated_region(painter, rect)

        painter.restore()

    def _draw_arrow(self, painter: QPainter, start: QPoint, end: QPoint, color: QColor, thickness: int) -> None:
        pen = QPen(color, thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(start, end)

        dx = end.x() - start.x()
        dy = end.y() - start.y()
        angle = math.atan2(dy, dx)
        head_len = max(12, thickness * 3.8)
        head_angle = math.pi / 6.5

        p1 = QPointF(end.x() - head_len * math.cos(angle - head_angle), end.y() - head_len * math.sin(angle - head_angle))
        p2 = QPointF(end.x() - head_len * math.cos(angle + head_angle), end.y() - head_len * math.sin(angle + head_angle))
        poly = QPolygonF([QPointF(end), p1, p2])
        painter.setBrush(QBrush(color))
        painter.drawPolygon(poly)

    def _draw_pixelated_region(self, painter: QPainter, rect: QRect) -> None:
        logical_size = self.working_pixmap.deviceIndependentSize().toSize()
        bounded = rect.intersected(QRect(QPoint(), logical_size))
        if bounded.width() <= 2 or bounded.height() <= 2:
            return
        sub = crop_pixmap(self.working_pixmap, bounded)
        small_w = max(1, bounded.width() // 10)
        small_h = max(1, bounded.height() // 10)
        small = sub.scaled(small_w, small_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        pixelated = small.scaled(
            bounded.width(),
            bounded.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter.drawPixmap(QRectF(bounded), pixelated, QRectF(pixelated.rect()))

    def _get_handle_rects(self, sel: QRect) -> dict:
        s = self.HANDLE_SIZE
        hs = s // 2
        cx = sel.center().x()
        cy = sel.center().y()
        return {
            "tl": QRect(sel.left() - hs, sel.top() - hs, s, s),
            "tr": QRect(sel.right() - hs, sel.top() - hs, s, s),
            "bl": QRect(sel.left() - hs, sel.bottom() - hs, s, s),
            "br": QRect(sel.right() - hs, sel.bottom() - hs, s, s),
            "t": QRect(cx - hs, sel.top() - hs, s, s),
            "b": QRect(cx - hs, sel.bottom() - hs, s, s),
            "l": QRect(sel.left() - hs, cy - hs, s, s),
            "r": QRect(sel.right() - hs, cy - hs, s, s),
        }

    def _hit_test_handle(self, pos: QPoint) -> Optional[str]:
        if self.selection_rect.isNull():
            return None
        for name, h_rect in self._get_handle_rects(self.selection_rect.normalized()).items():
            if h_rect.adjusted(-4, -4, 4, 4).contains(pos):
                return name
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            if not self.selection_rect.isNull():
                self.selection_rect = QRect()
                self.annotations.clear()
                self.redo_stack.clear()
                self.step_counter_value = 1
                self.tools_bar.hide()
                self.actions_bar.hide()
                self.update()
            else:
                self.finish_and_close()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position().toPoint()
        self.current_mouse_pos = pos
        sel = self.selection_rect.normalized()

        handle = self._hit_test_handle(pos)
        if handle is not None and self.current_tool == ToolType.SELECT_MOVE:
            self.active_resize_handle = handle
            self.drag_origin = pos
            self.rect_at_drag_start = sel
            self.tools_bar.hide()
            self.actions_bar.hide()
            return

        if sel.isNull() or sel.width() < 5 or sel.height() < 5:
            self.is_selecting = True
            self.drag_origin = pos
            self.selection_rect = QRect(pos, pos)
            self.potential_snap_window = self.hovered_window
            self.tools_bar.hide()
            self.actions_bar.hide()
            self.update()
            return

        if self.current_tool != ToolType.SELECT_MOVE and sel.contains(pos):
            if self.current_tool == ToolType.TEXT:
                text, ok = QInputDialog.getText(self, "Add Text Annotation", "Enter text:")
                if ok and text.strip():
                    item = AnnotationItem(
                        tool=ToolType.TEXT,
                        color=QColor(self.current_color),
                        thickness=self.current_thickness,
                        start=pos,
                        text=text.strip(),
                    )
                    self.annotations.append(item)
                    self.redo_stack.clear()
                    self.update()
                return

            if self.current_tool == ToolType.STEP_COUNTER:
                item = AnnotationItem(
                    tool=ToolType.STEP_COUNTER,
                    color=QColor(self.current_color),
                    thickness=self.current_thickness,
                    start=pos,
                    step_number=self.step_counter_value,
                )
                self.step_counter_value += 1
                self.annotations.append(item)
                self.redo_stack.clear()
                self.update()
                return

            self.active_annotation = AnnotationItem(
                tool=self.current_tool,
                color=QColor(self.current_color),
                thickness=self.current_thickness,
                start=pos,
                end=pos,
                points=[pos],
            )
            self.update()
            return

        if sel.contains(pos) and self.current_tool == ToolType.SELECT_MOVE:
            self.is_moving_selection = True
            self.drag_origin = pos
            self.rect_at_drag_start = sel
            self.tools_bar.hide()
            self.actions_bar.hide()
            return

        if self.current_tool == ToolType.SELECT_MOVE:
            self.is_selecting = True
            self.drag_origin = pos
            self.selection_rect = QRect(pos, pos)
            self.potential_snap_window = None
            self.hovered_window = None
            self.annotations.clear()
            self.redo_stack.clear()
            self.step_counter_value = 1
            self.tools_bar.hide()
            self.actions_bar.hide()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        self.current_mouse_pos = pos

        # If actively dragging to select custom area:
        if self.is_selecting:
            if (pos - self.drag_origin).manhattanLength() > 3:
                self.hovered_window = None
                self.potential_snap_window = None
            self.selection_rect = QRect(self.drag_origin, pos).normalized().intersected(self.rect())
            self.update()
            return

        # Smart Window Snap Detection when no selection is active
        if self.selection_rect.isNull() and not self.is_selecting and self.config.auto_snap_windows:
            found_win = None
            for w_rect, w_title in self.detected_windows:
                if w_rect.contains(pos):
                    found_win = (w_rect, w_title)
                    break
            if found_win != self.hovered_window:
                self.hovered_window = found_win
                self.update()

        if self.active_resize_handle is not None:
            r = QRect(self.rect_at_drag_start)
            h = self.active_resize_handle
            if "l" in h:
                r.setLeft(pos.x())
            if "r" in h:
                r.setRight(pos.x())
            if "t" in h:
                r.setTop(pos.y())
            if "b" in h:
                r.setBottom(pos.y())
            self.selection_rect = r.normalized().intersected(self.rect())
            self.update()
            return

        if self.is_moving_selection:
            delta = pos - self.drag_origin
            moved = self.rect_at_drag_start.translated(delta)
            if moved.left() < 0:
                moved.moveLeft(0)
            if moved.top() < 0:
                moved.moveTop(0)
            if moved.right() >= self.width():
                moved.moveRight(self.width() - 1)
            if moved.bottom() >= self.height():
                moved.moveBottom(self.height() - 1)
            self.selection_rect = moved
            self.update()
            return

        if self.active_annotation is not None:
            self.active_annotation.end = pos
            if self.active_annotation.tool in (ToolType.PEN, ToolType.HIGHLIGHTER):
                self.active_annotation.points.append(pos)
            self.update()
            return

        if self.current_tool == ToolType.SELECT_MOVE:
            handle = self._hit_test_handle(pos)
            if handle in ("tl", "br"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif handle in ("tr", "bl"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif handle in ("t", "b"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif handle in ("l", "r"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif self.selection_rect.normalized().contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

        if self.selection_rect.isNull():
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.is_selecting:
            self.is_selecting = False
            norm = self.selection_rect.normalized()
            # If the user dragged a custom area (at least 6x6 pixels)
            if norm.width() >= 6 and norm.height() >= 6:
                self.selection_rect = norm
                self.hovered_window = None
                self.potential_snap_window = None

                # Dedicated OCR Mode: extract directly on release!
                if self.ocr_mode:
                    self.action_extract_ocr_text()
                    return
                if self.scroll_mode:
                    self.action_start_scroll_capture()
                    return
                if getattr(self, "gif_mode", False):
                    self.action_start_gif_recording()
                    return

                self._position_toolbars()
                if self.config.auto_copy_clipboard and not self.multi_mode:
                    QApplication.clipboard().setPixmap(self.render_final_crop())
            # If the user clicked once in place without dragging:
            elif self.potential_snap_window is not None:
                self.selection_rect = self.potential_snap_window[0].intersected(self.rect())
                self.hovered_window = None
                self.potential_snap_window = None
                if self.ocr_mode:
                    self.action_extract_ocr_text()
                    return
                if self.scroll_mode:
                    self.action_start_scroll_capture()
                    return
                if getattr(self, "gif_mode", False):
                    self.action_start_gif_recording()
                    return
                self._position_toolbars()
                if self.config.auto_copy_clipboard and not self.multi_mode:
                    QApplication.clipboard().setPixmap(self.render_final_crop())
            else:
                self.selection_rect = QRect()
                self.hovered_window = None
                self.potential_snap_window = None
                self.tools_bar.hide()
                self.actions_bar.hide()
            self.update()
            return

        if self.active_resize_handle is not None or self.is_moving_selection:
            self.active_resize_handle = None
            self.is_moving_selection = False
            self.selection_rect = self.selection_rect.normalized()
            self._position_toolbars()
            if self.config.auto_copy_clipboard and self.selection_rect.width() > 10 and not self.multi_mode:
                QApplication.clipboard().setPixmap(self.render_final_crop())
            self.update()
            return

        if self.active_annotation is not None:
            self.annotations.append(self.active_annotation)
            self.redo_stack.clear()
            self.active_annotation = None
            if self.config.auto_copy_clipboard and not self.multi_mode:
                QApplication.clipboard().setPixmap(self.render_final_crop())
            self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if not self.selection_rect.isNull() and self.selection_rect.width() > 5:
            self.action_copy_clipboard()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self.finish_and_close()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.action_copy_clipboard()
        elif key == Qt.Key.Key_T and mods & Qt.KeyboardModifier.ControlModifier:
            self.action_extract_ocr_text()
        elif key == Qt.Key.Key_C and mods & Qt.KeyboardModifier.ControlModifier:
            self.action_copy_clipboard()
        elif key == Qt.Key.Key_S and mods & Qt.KeyboardModifier.ControlModifier:
            self.action_save_as()
        elif key == Qt.Key.Key_D and mods & Qt.KeyboardModifier.ControlModifier:
            self.action_quick_save()
        elif key == Qt.Key.Key_P and mods & Qt.KeyboardModifier.ControlModifier:
            self.action_pin_to_screen()
        elif key == Qt.Key.Key_M and mods & Qt.KeyboardModifier.ControlModifier:
            self._toggle_multi_mode()
        elif key == Qt.Key.Key_Z and mods & Qt.KeyboardModifier.ControlModifier:
            self.undo_annotation()
        elif key == Qt.Key.Key_Y and mods & Qt.KeyboardModifier.ControlModifier:
            self.redo_annotation()
        elif key == Qt.Key.Key_C and not mods:
            img = self._sample_image
            scale = self.working_pixmap.devicePixelRatio()
            sample = QPoint(round(self.current_mouse_pos.x() * scale), round(self.current_mouse_pos.y() * scale))
            if img.rect().contains(sample):
                hex_val = img.pixelColor(sample).name().upper()
                QApplication.clipboard().setText(hex_val)
                self.notification_requested.emit("Color Copied", f"Copied HEX color {hex_val} to clipboard!")
        elif not mods:
            shortcut_map = {
                Qt.Key.Key_M: ToolType.SELECT_MOVE,
                Qt.Key.Key_P: ToolType.PEN,
                Qt.Key.Key_L: ToolType.LINE,
                Qt.Key.Key_A: ToolType.ARROW,
                Qt.Key.Key_R: ToolType.RECTANGLE,
                Qt.Key.Key_E: ToolType.ELLIPSE,
                Qt.Key.Key_H: ToolType.HIGHLIGHTER,
                Qt.Key.Key_T: ToolType.TEXT,
                Qt.Key.Key_N: ToolType.STEP_COUNTER,
                Qt.Key.Key_B: ToolType.PIXELATE,
                Qt.Key.Key_K: ToolType.REDACT,
            }
            if key in shortcut_map:
                self.select_tool(shortcut_map[key])

    def undo_annotation(self) -> None:
        if self.annotations:
            self.redo_stack.append(self.annotations.pop())
            self._sync_step_counter()
            self.update()

    def redo_annotation(self) -> None:
        if self.redo_stack:
            self.annotations.append(self.redo_stack.pop())
            self._sync_step_counter()
            self.update()

    def _sync_step_counter(self):
        self.step_counter_value = max((item.step_number for item in self.annotations
                                       if item.tool == ToolType.STEP_COUNTER), default=0) + 1

    def render_final_crop(self):
        sel = self.selection_rect.normalized().intersected(self.rect())
        if sel.width() < 2 or sel.height() < 2:
            return QPixmap()
        canvas = crop_pixmap(self.working_pixmap, sel)
        if canvas.isNull():
            return canvas
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(-sel.left(), -sel.top())
        for item in self.annotations:
            self._draw_annotation(painter, item)
        painter.end()
        return canvas

    def action_extract_ocr_text(self):
        cropped = self.render_final_crop()
        if not cropped.isNull():
            self.ocr_requested.emit(cropped.toImage())
            self.close()

    def action_start_scroll_capture(self):
        sel = self.selection_rect.normalized()
        if self.editor_mode or sel.width() < 20 or sel.height() < 20:
            self.notification_requested.emit("Scroll Capture", "Select a screen region at least 20 × 20 pixels.")
            return
        self.scroll_capture_requested.emit(sel.translated(self.virtual_rect.topLeft()))
        self.close()

    def action_start_gif_recording(self):
        sel = self.selection_rect.normalized()
        if self.editor_mode or sel.width() < 20 or sel.height() < 20:
            self.notification_requested.emit("Screen Recorder", "Select a screen region at least 20 × 20 pixels.")
            return
        self.gif_record_requested.emit(sel.translated(self.virtual_rect.topLeft()))
        self.close()


    def _prepare_next_multi_snip(self, crop: QPixmap) -> None:
        if sum(p.width() * p.height() for p in self.captured_crops) + crop.width() * crop.height() > MAX_IMAGE_PIXELS:
            self.notification_requested.emit("Multi-Snip", "48 megapixel limit reached. Press Finish to combine current snips.")
            return
        self.captured_crops.append(crop)
        self._update_multi_btn_style()
        self.selection_rect = QRect()
        self.annotations.clear()
        self.redo_stack.clear()
        self.step_counter_value = 1
        self.tools_bar.hide()
        self.actions_bar.hide()
        self.update()

    def action_copy_clipboard(self) -> None:
        cropped = self.render_final_crop()
        if cropped.isNull():
            return
        QApplication.clipboard().setPixmap(cropped)

        if self.multi_mode:
            self._prepare_next_multi_snip(cropped)
            self.notification_requested.emit(
                f"Multi-Snip #{len(self.captured_crops)} Copied",
                f"Snip #{len(self.captured_crops)} copied to clipboard! Select next area or press Esc.",
            )
        else:
            self.notification_requested.emit(
                "Screenshot Copied",
                f"Copied {cropped.width()}×{cropped.height()} px screenshot to clipboard.",
            )
            self.close()

    def action_pin_to_screen(self) -> None:
        cropped = self.render_final_crop()
        if cropped.isNull():
            return
        pin_win = PinnedScreenshotWindow(cropped)
        sel = self.selection_rect.normalized()
        if not sel.isNull():
            pin_win.move(self.virtual_rect.topLeft() + sel.topLeft())
        pin_win.show()
        self.pinned_created.emit(pin_win)

        if self.multi_mode:
            self._prepare_next_multi_snip(cropped)
        else:
            self.close()

    def action_quick_save(self):
        cropped = self.render_final_crop()
        if cropped.isNull():
            return
        try:
            path = save_image(cropped, self.config.save_directory, self.config.image_format)
        except (OSError, ValueError) as error:
            self.notification_requested.emit("Save failed", str(error))
            QMessageBox.warning(self, "Save failed", str(error))
            return
        self.notification_requested.emit("Screenshot saved", str(path))
        if self.multi_mode:
            self._prepare_next_multi_snip(cropped)
        else:
            self.close()

    def action_save_as(self):
        cropped = self.render_final_crop()
        if cropped.isNull():
            return
        fmt = self.config.image_format.lower()
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save screenshot", str(pathlib.Path(self.config.save_directory) / f"Screenshot.{fmt}"),
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp)")
        if not path:
            return
        selected_format = "JPG" if selected_filter.startswith("JPEG") else "WEBP" if selected_filter.startswith("WebP") else "PNG"
        try:
            saved = save_image(cropped, self.config.save_directory, selected_format, path=path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Save failed", str(error))
            return
        self.notification_requested.emit("Screenshot saved", str(saved))
        if self.multi_mode:
            self._prepare_next_multi_snip(cropped)
        else:
            self.close()

    def finish_and_close(self) -> None:
        if self.captured_crops:
            self.multicapture_finished.emit(self.captured_crops)
        self.close()


# ============================================================================
# 11. SETTINGS DIALOG WITH CUSTOM HOTKEY RECORDER
# ============================================================================

class CustomKeyCaptureEdit(QKeySequenceEdit):
    def __init__(self, sequence):
        super().__init__(sequence)
        self.setMaximumSequenceLength(1)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Print, Qt.Key.Key_SysReq):
            self.setKeySequence(QKeySequence("Print"))
            event.accept()
            return
        super().keyPressEvent(event)


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("SnapShot Pro — Settings & Custom Shortcuts")
        self.setWindowIcon(get_app_icon())
        self.setMinimumWidth(500)

        self.setStyleSheet("""
            QDialog {
                background-color: #0F172A;
                color: #F8FAFC;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QKeySequenceEdit {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QCheckBox {
                color: #E2E8F0;
                font-size: 13px;
                spacing: 8px;
            }
            QPushButton {
                background-color: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel("⌨️ Custom Shortcuts & Advanced Features")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #38BDF8;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(12)

        self.primary_key_edit = CustomKeyCaptureEdit(QKeySequence(self.config.hotkey_region))
        btn_set_print = QPushButton("Use PrintScreen")
        btn_set_print.clicked.connect(lambda: self.primary_key_edit.setKeySequence(QKeySequence("Print")))
        row_primary = QHBoxLayout()
        row_primary.addWidget(self.primary_key_edit, 1)
        row_primary.addWidget(btn_set_print)
        form.addRow("Primary Capture Key:", row_primary)

        self.secondary_key_edit = CustomKeyCaptureEdit(QKeySequence(self.config.hotkey_secondary))
        form.addRow("Custom Region Shortcut:", self.secondary_key_edit)

        self.fullscreen_key_edit = CustomKeyCaptureEdit(QKeySequence(self.config.hotkey_fullscreen))
        form.addRow("Full Screen Shortcut:", self.fullscreen_key_edit)

        self.multi_key_edit = CustomKeyCaptureEdit(QKeySequence(self.config.hotkey_multicapture))
        form.addRow("Multi-Capture Shortcut:", self.multi_key_edit)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPG", "WEBP"])
        self.format_combo.setCurrentText(self.config.image_format)
        form.addRow("Default Image Format:", self.format_combo)

        self.ocr_language_edit = QLineEdit(self.config.ocr_language)
        self.ocr_language_edit.setToolTip("Installed Tesseract languages, for example eng, urd, or eng+urd")
        form.addRow("OCR languages:", self.ocr_language_edit)

        self.dir_edit = QLineEdit(self.config.save_directory)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse_btn)
        form.addRow("Quick Save Folder:", dir_row)

        layout.addLayout(form)

        # Advanced Toggles
        self.auto_snap_chk = QCheckBox("[Feature 4] Smart Window Auto-Snap: Highlight and snap windows on hover")
        self.auto_snap_chk.setChecked(self.config.auto_snap_windows)
        layout.addWidget(self.auto_snap_chk)

        self.auto_copy_chk = QCheckBox("Automatically copy selection to clipboard on mouse release")
        self.auto_copy_chk.setChecked(self.config.auto_copy_clipboard)
        layout.addWidget(self.auto_copy_chk)

        self.magnifier_chk = QCheckBox("Show pixel magnifier loupe & live HEX color picker")
        self.magnifier_chk.setChecked(self.config.show_magnifier)
        layout.addWidget(self.magnifier_chk)

        self.autostart_chk = QCheckBox("Start SnapShot Pro automatically on Windows startup (PC restart)")
        self.autostart_chk.setChecked(self.config.autostart_enabled)
        layout.addWidget(self.autostart_chk)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setStyleSheet("background-color: #4F46E5; border-color: #6366F1; color: white;")
        save_btn.clicked.connect(self._save_settings)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        copyright_lbl = QLabel("© 2026 SnapShot Pro • Lyaritech. All rights reserved.")
        copyright_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_lbl.setStyleSheet("font-size: 11px; color: #475569; padding-top: 4px;")
        layout.addWidget(copyright_lbl)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Quick Save Folder", self.dir_edit.text())
        if folder:
            self.dir_edit.setText(folder)

    def _reset_defaults(self) -> None:
        # Reset the form only. Cancel must preserve the user's saved preferences.
        self.primary_key_edit.setKeySequence(QKeySequence("Print"))
        self.secondary_key_edit.setKeySequence(QKeySequence("Ctrl+Shift+S"))
        self.fullscreen_key_edit.setKeySequence(QKeySequence("Ctrl+Shift+F"))
        self.multi_key_edit.setKeySequence(QKeySequence("Ctrl+Shift+M"))
        self.format_combo.setCurrentText("PNG")
        self.ocr_language_edit.setText("eng")
        self.dir_edit.setText(str(pathlib.Path.home() / "Pictures" / "SnapShotPro"))
        self.auto_snap_chk.setChecked(False)
        self.auto_copy_chk.setChecked(False)
        self.magnifier_chk.setChecked(True)
        self.autostart_chk.setChecked(True)

    def _save_settings(self) -> None:
        import re
        from snapshot_native import windows_hotkey
        sequences = [field.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                     for field in (self.primary_key_edit, self.secondary_key_edit,
                                   self.fullscreen_key_edit, self.multi_key_edit)]
        try:
            if len({seq.lower() for seq in sequences}) != 4:
                raise ValueError("Choose a different shortcut for each action.")
            for sequence in sequences:
                windows_hotkey(sequence)
            language = self.ocr_language_edit.text().strip()
            if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", language):
                raise ValueError("Use installed OCR language codes, for example eng+urd.")
            directory = pathlib.Path(self.dir_edit.text().strip()).expanduser()
            if not self.dir_edit.text().strip():
                raise ValueError("Choose a screenshot folder.")
            directory.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Check settings", str(error))
            return
        self.config.hotkey_region = self.primary_key_edit.keySequence().toString() or "Print"
        self.config.hotkey_secondary = self.secondary_key_edit.keySequence().toString() or "Ctrl+Shift+S"
        self.config.hotkey_fullscreen = self.fullscreen_key_edit.keySequence().toString() or "Ctrl+Shift+F"
        self.config.hotkey_multicapture = self.multi_key_edit.keySequence().toString() or "Ctrl+Shift+M"
        self.config.image_format = self.format_combo.currentText()
        self.config.save_directory = str(directory)
        self.config.ocr_language = language
        self.config.auto_snap_windows = self.auto_snap_chk.isChecked()
        self.config.auto_copy_clipboard = self.auto_copy_chk.isChecked()
        self.config.show_magnifier = self.magnifier_chk.isChecked()
        self.config.autostart_enabled = self.autostart_chk.isChecked()

        self.settings_saved.emit()
        self.accept()


# ============================================================================
# 12. MAIN CONTROL PANEL & CONTROLLER
# ============================================================================

class SnapShotController(QMainWindow):
    """Main application controller with OCR, Scrolling Capture, and Auto-Snap."""

    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig()
        self._capture_pending = False
        self._restore_after_work = False
        self._quitting = False
        self._jobs = set()
        self._dialogs = []
        QThreadPool.globalInstance().setMaxThreadCount(2)
        self.app_icon = get_app_icon()
        self.active_overlay: Optional[CaptureOverlay] = None
        self.active_scroll_ctrl: Optional[ScrollingCaptureController] = None
        self.active_recorder_ctrl: Optional[ScreenRecorderController] = None
        self.pinned_windows: List[PinnedScreenshotWindow] = []

        self.setWindowTitle("SnapShot Pro — Advanced Screenshot Suite")
        self.setWindowIcon(self.app_icon)
        self.resize(620, 680)
        self.setMinimumSize(560, 630)

        self._build_ui()
        self._setup_system_tray()

        self.hotkey_manager = GlobalHotkeyManager(self.config, self)
        self.hotkey_manager.trigger_region.connect(self.start_region_capture)
        self.hotkey_manager.trigger_fullscreen.connect(self.capture_fullscreen_instant)
        self.hotkey_manager.trigger_multicapture.connect(self.start_multi_capture)
        self._refresh_labels()
        if self.hotkey_manager.failures:
            self.show_notification("Shortcut status", "; ".join(self.hotkey_manager.failures)[:300])

        self._app_shortcuts: List[QShortcut] = []
        self._register_window_shortcuts()

    def _build_ui(self):
        self.setWindowTitle(f"SnapShot Pro {VERSION}")
        self.setStyleSheet("""
            QMainWindow, QWidget#Panel { background: #0b1220; }
            QLabel { color: #edf3fc; background: transparent; }
            QPushButton { background: #152237; color: #dce7f5; border: 1px solid #29394f;
                          border-radius: 9px; padding: 12px; font-size: 13px; text-align: left; }
            QPushButton:hover { background: #1e3049; border-color: #4e718f; }
            QPushButton:disabled { color: #5d7188; }
            QComboBox { background: #152237; color: #dce7f5; border: 1px solid #29394f;
                        border-radius: 6px; padding: 6px; }
            QMenu { background: #152237; color: #dce7f5; padding: 8px; }
            QMenu::item { padding: 8px 12px; }
            QMenu::item:selected { background: #28435c; }
        """)
        central = QWidget(self)
        central.setObjectName("Panel")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(14)
        brand = QHBoxLayout()
        title = QLabel("SNAPSHOT  <span style='color:#42dfc5'>PRO</span>")
        title.setStyleSheet("font-size: 19px; font-weight: 800; letter-spacing: 2px;")
        brand.addWidget(title)
        brand.addStretch()
        badge = QLabel(f"NATIVE DESKTOP  /  {VERSION}")
        badge.setStyleSheet("font-size: 10px; color: #8ea4bc;")
        brand.addWidget(badge)
        layout.addLayout(brand)
        headline = QLabel("Capture. Mark up. Keep moving.")
        headline.setStyleSheet("font-size: 26px; font-weight: 700;")
        layout.addWidget(headline)
        self.subtitle_lbl = QLabel("A precise capture, without interrupting your flow.")
        self.subtitle_lbl.setWordWrap(True)
        self.subtitle_lbl.setStyleSheet("font-size: 12px; color: #91a6bd;")
        layout.addWidget(self.subtitle_lbl)
        self.region_button = QPushButton("+   Capture a region                              PrintScreen")
        self.region_button.setMinimumHeight(66)
        self.region_button.setStyleSheet("background: #2dd4b4; color: #05251e; border: 0; font-size: 16px; font-weight: 700;")
        self.region_button.clicked.connect(self.start_region_capture)
        layout.addWidget(self.region_button)
        grid = QGridLayout()
        grid.setSpacing(10)
        actions = [
            ("↕   Scrolling capture", "Manual frames or automatic scroll with overlap detection", self.start_scrolling_capture),
            ("🎥   Record to GIF", "Select a screen area and record animated GIF", self.start_gif_capture),
            ("T   Text grabber", "Extract text locally with Tesseract OCR", self.start_ocr_capture),
            ("▦   Multi-snip", "Collect several regions and combine them vertically", self.start_multi_capture),
            ("▣   Full desktop", "Copy and save all screens in one image", self.capture_fullscreen_instant),
            ("▤   Each monitor", "Save each monitor as a separate image", self.capture_all_monitors_split),
            ("◷   Delayed capture", "Choose a delay below, then capture a region", self._start_selected_delay),
        ]
        for index, (label, hint, callback) in enumerate(actions):
            button = QPushButton(label)
            button.setToolTip(hint)
            button.setMinimumHeight(47)
            button.clicked.connect(callback)
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)
        row = QHBoxLayout()
        hint = QLabel("IMAGE WORKSPACE")
        hint.setStyleSheet("font-size: 10px; color: #8299b2; letter-spacing: 1px;")
        row.addWidget(hint)
        row.addStretch()
        label = QLabel("Delay")
        label.setStyleSheet("color: #8ea4bc; font-size: 11px;")
        row.addWidget(label)
        self.delay_combo = QComboBox()
        for seconds in (3, 5, 10):
            self.delay_combo.addItem(f"{seconds}s", seconds * 1000)
        row.addWidget(self.delay_combo)
        layout.addLayout(row)
        editor_row = QHBoxLayout()
        for label, callback in (("Open image", self.open_image), ("Paste image", self.paste_image)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            editor_row.addWidget(button)
        recent = QPushButton("Recent saves ▾")
        menu = QMenu(recent)
        menu.aboutToShow.connect(lambda: self._populate_recents(menu))
        recent.setMenu(menu)
        editor_row.addWidget(recent)
        layout.addLayout(editor_row)
        self.status_label = QLabel("Ready • images stay on your device")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(42)
        self.status_label.setStyleSheet("background: #101d2e; color: #9ab3cb; padding: 10px; border-radius: 8px; font-size: 11px;")
        layout.addWidget(self.status_label)
        footer = QHBoxLayout()
        settings = QPushButton("Settings && shortcuts")
        settings.clicked.connect(self.open_settings)
        footer.addWidget(settings)
        folder = QPushButton("Saved files")
        folder.clicked.connect(self.open_screenshots_folder)
        footer.addWidget(folder)
        self.tray_button = QPushButton("To tray")
        self.tray_button.clicked.connect(self.hide_to_tray)
        footer.addWidget(self.tray_button)
        layout.addLayout(footer)
        layout.addStretch()

        copyright_lbl = QLabel("© 2026 SnapShot Pro • Lyaritech. All rights reserved.")
        copyright_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_lbl.setStyleSheet("font-size: 11px; color: #4e637a; padding-top: 6px;")
        layout.addWidget(copyright_lbl)

    def _start_selected_delay(self):
        self.start_delayed_capture(self.delay_combo.currentData())

    def _populate_recents(self, menu):
        menu.clear()
        directory = pathlib.Path(self.config.save_directory)
        try:
            paths = sorted((p for p in directory.iterdir() if p.is_file() and
                            p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}),
                           key=lambda p: p.stat().st_mtime, reverse=True)[:12]
        except OSError:
            paths = []
        for path in paths:
            menu.addAction(path.name, lambda checked=False, p=path: self._load_image(p))
        if not paths:
            menu.addAction("No saved screenshots yet").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Open saved files folder", self.open_screenshots_folder)

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open image", self.config.save_directory,
                                             "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._load_image(path)

    def _load_image(self, path):
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.width() * size.height() > MAX_IMAGE_PIXELS:
            self.show_notification("Image too large", "Open an image smaller than 48 megapixels.")
            return
        image = reader.read()
        if image.isNull():
            self.show_notification("Cannot open image", reader.errorString())
            return
        self._open_editor(QPixmap.fromImage(image))

    def paste_image(self):
        pixmap = QApplication.clipboard().pixmap()
        if pixmap.isNull():
            self.show_notification("Clipboard", "Copy an image first, then choose Paste image.")
            return
        if pixmap.width() * pixmap.height() > MAX_IMAGE_PIXELS:
            self.show_notification("Image too large", "Paste an image smaller than 48 megapixels.")
            return
        self._open_editor(pixmap)

    def _open_editor(self, pixmap):
        if self.active_overlay is not None or self._capture_pending:
            return
        available = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        scale = max(1.0, pixmap.width() / min(1000, available.width() - 80),
                    pixmap.height() / max(160, available.height() - 160))
        pixmap = QPixmap(pixmap)
        pixmap.setDevicePixelRatio(scale)
        size = pixmap.deviceIndependentSize().toSize()
        width = min(available.width(), max(600, size.width()))
        height = min(available.height() - 60, max(300, size.height()))
        rect = QRect(available.center().x() - width // 2, available.center().y() - height // 2, width, height)
        self._restore_after_work = self._restore_after_work or self.isVisible()
        self.hide()
        overlay = CaptureOverlay(pixmap, rect, self.config)
        overlay.editor_mode = True
        overlay.setWindowFlags(Qt.WindowType.Window)
        overlay.setWindowTitle("SnapShot Pro — Image editor")
        overlay.setStyleSheet("background: #0b1220;")
        overlay.scroll_btn.setEnabled(False)
        overlay.selection_rect = QRect(QPoint(), size)
        self._attach_overlay(overlay)
        overlay._position_toolbars()

    def _setup_system_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("SnapShot Pro — Double-click to Open")

        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet("""
            QMenu {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #334155;
                padding: 6px;
                border-radius: 8px;
            }
            QMenu::item {
                padding: 7px 22px 7px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #334155;
                color: #38BDF8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #334155;
                margin: 5px 8px;
            }
        """)

        # 1. Main Action: Open Control Panel (Default action on double-click)
        self.act_tray_panel = QAction("🎛️ Open Control Panel", self)
        f = self.act_tray_panel.font()
        f.setBold(True)
        self.act_tray_panel.setFont(f)
        self.act_tray_panel.triggered.connect(self.show_normal_window)
        self.tray_menu.addAction(self.act_tray_panel)
        self.tray_menu.setDefaultAction(self.act_tray_panel)

        self.tray_menu.addSeparator()

        # 2. Capture Actions
        self.act_tray_region = QAction("✂️ Capture Region (Auto-Snap)", self)
        self.act_tray_region.triggered.connect(self.start_region_capture)
        self.tray_menu.addAction(self.act_tray_region)

        self.act_tray_scroll = QAction("📜 Scrolling Long Capture", self)
        self.act_tray_scroll.triggered.connect(self.start_scrolling_capture)
        self.tray_menu.addAction(self.act_tray_scroll)

        self.act_tray_gif = QAction("🎥 Record Screen to GIF", self)
        self.act_tray_gif.triggered.connect(self.start_gif_capture)
        self.tray_menu.addAction(self.act_tray_gif)

        self.act_tray_ocr = QAction("📝 Extract OCR Text from Screen", self)
        self.act_tray_ocr.triggered.connect(self.start_ocr_capture)
        self.tray_menu.addAction(self.act_tray_ocr)

        self.act_tray_multi = QAction("🔁 Multiple Consecutive Snips", self)
        self.act_tray_multi.triggered.connect(self.start_multi_capture)
        self.tray_menu.addAction(self.act_tray_multi)

        self.act_tray_full = QAction("🖥️ Capture Full Screen", self)
        self.act_tray_full.triggered.connect(self.capture_fullscreen_instant)
        self.tray_menu.addAction(self.act_tray_full)

        self.act_tray_monitors = QAction("🖥️🖥️ Capture All Monitors", self)
        self.act_tray_monitors.triggered.connect(self.capture_all_monitors_split)
        self.tray_menu.addAction(self.act_tray_monitors)

        self.tray_menu.addSeparator()

        # 3. Quick Toggles Submenu (Directly Manage Functions from Tray)
        self.quick_menu = self.tray_menu.addMenu("⚡ Quick Toggles")
        self.quick_menu.setStyleSheet(self.tray_menu.styleSheet())

        self.act_toggle_snap = QAction("Smart Window Auto-Snap", self)
        self.act_toggle_snap.setCheckable(True)
        self.act_toggle_snap.setChecked(self.config.auto_snap_windows)
        self.act_toggle_snap.triggered.connect(self._toggle_tray_snap)
        self.quick_menu.addAction(self.act_toggle_snap)

        self.act_toggle_copy = QAction("Auto-Copy to Clipboard", self)
        self.act_toggle_copy.setCheckable(True)
        self.act_toggle_copy.setChecked(self.config.auto_copy_clipboard)
        self.act_toggle_copy.triggered.connect(self._toggle_tray_copy)
        self.quick_menu.addAction(self.act_toggle_copy)

        self.act_toggle_mag = QAction("Show Magnifier Loupe", self)
        self.act_toggle_mag.setCheckable(True)
        self.act_toggle_mag.setChecked(self.config.show_magnifier)
        self.act_toggle_mag.triggered.connect(self._toggle_tray_mag)
        self.quick_menu.addAction(self.act_toggle_mag)

        # 4. Utilities
        act_folder = QAction("📂 Open Screenshots Folder", self)
        act_folder.triggered.connect(self.open_screenshots_folder)
        self.tray_menu.addAction(act_folder)

        act_settings = QAction("⚙️ Settings & Custom Hotkeys...", self)
        act_settings.triggered.connect(self.open_settings)
        self.tray_menu.addAction(act_settings)

        self.tray_menu.addSeparator()

        # 5. Quit
        act_quit = QAction("❌ Quit SnapShot Pro", self)
        act_quit.triggered.connect(self.quit_application)
        self.tray_menu.addAction(act_quit)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        self.tray_button.setEnabled(QSystemTrayIcon.isSystemTrayAvailable())
        self._refresh_tray_menu_labels()

    def _toggle_tray_snap(self, checked: bool) -> None:
        self.config.auto_snap_windows = checked
        status = "Enabled" if checked else "Disabled"
        self.show_notification("Smart Window Auto-Snap", f"Window snap detection is now {status}.")

    def _toggle_tray_copy(self, checked: bool) -> None:
        self.config.auto_copy_clipboard = checked
        status = "Enabled" if checked else "Disabled"
        self.show_notification("Auto-Copy to Clipboard", f"Auto-copy is now {status}.")

    def _toggle_tray_mag(self, checked: bool) -> None:
        self.config.show_magnifier = checked
        status = "Enabled" if checked else "Disabled"
        self.show_notification("Magnifier Loupe", f"Magnifier loupe is now {status}.")

    def open_screenshots_folder(self) -> None:
        """Opens user screenshots directory in OS file manager."""
        save_dir = pathlib.Path(self.config.save_directory)
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.show_notification("Cannot open folder", str(error))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(save_dir)))

    def _refresh_labels(self) -> None:
        engine = "MSS + Qt" if HAS_MSS else "Qt Native"
        self.region_button.setText(f"+   Capture a region                         {self.config.hotkey_region}")
        self.subtitle_lbl.setText(
            f"Engine: {engine}  •  Snip: [{self.config.hotkey_region}]  •  "
            f"Multi: [{self.config.hotkey_multicapture}]  •  Full: [{self.config.hotkey_fullscreen}]"
        )

    def _refresh_tray_menu_labels(self) -> None:
        self.act_tray_region.setText(f"✂️ Capture Region ({self.config.hotkey_region})")
        self.act_tray_multi.setText(f"🔁 Multiple Snips ({self.config.hotkey_multicapture})")
        self.act_tray_full.setText(f"🖥️ Full Screen ({self.config.hotkey_fullscreen})")
        if hasattr(self, "act_toggle_snap"):
            self.act_toggle_snap.setChecked(self.config.auto_snap_windows)
        if hasattr(self, "act_toggle_copy"):
            self.act_toggle_copy.setChecked(self.config.auto_copy_clipboard)
        if hasattr(self, "act_toggle_mag"):
            self.act_toggle_mag.setChecked(self.config.show_magnifier)

    def _register_window_shortcuts(self) -> None:
        for sc in self._app_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._app_shortcuts.clear()
        # RegisterHotKey/pynput also fires while this window is focused.
        if self.hotkey_manager.available:
            return

        for seq in (self.config.hotkey_region, self.config.hotkey_secondary):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(self.start_region_capture)
            self._app_shortcuts.append(sc)

        sc_multi = QShortcut(QKeySequence(self.config.hotkey_multicapture), self)
        sc_multi.activated.connect(self.start_multi_capture)
        self._app_shortcuts.append(sc_multi)

        sc_full = QShortcut(QKeySequence(self.config.hotkey_fullscreen), self)
        sc_full.activated.connect(self.capture_fullscreen_instant)
        self._app_shortcuts.append(sc_full)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Left-click or double-click restores and brings the main window to front."""
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_normal_window()

    def start_region_capture(self) -> None:
        self._launch_overlay(multi_mode=False)

    def start_multi_capture(self) -> None:
        self._launch_overlay(multi_mode=True)

    def start_ocr_capture(self) -> None:
        """Launches overlay in dedicated OCR mode: drag any region and text is extracted instantly."""
        self.show_notification("OCR Text Grabber", "Drag over any text on screen to extract and copy it.")
        self._launch_overlay(multi_mode=False, ocr_mode=True)

    def start_scrolling_capture(self):
        self._launch_overlay(scroll_mode=True)

    def start_gif_capture(self):
        self.show_notification("Screen Recorder", "Drag any screen area to record an animated GIF.")
        self._launch_overlay(gif_mode=True)

    def _launch_overlay(self, multi_mode=False, ocr_mode=False, scroll_mode=False, gif_mode=False):
        if (self._quitting or self._capture_pending or self.active_overlay is not None or
                self.active_scroll_ctrl is not None or self.active_recorder_ctrl is not None):
            return
        self._capture_pending = True
        self._restore_after_work = self._restore_after_work or self.isVisible()
        self.hide()
        # Wait for the compositor to remove our window before grabbing the desktop.
        QTimer.singleShot(180, lambda: self._do_launch_overlay(multi_mode, ocr_mode, scroll_mode, gif_mode))

    def _do_launch_overlay(self, multi_mode=False, ocr_mode=False, scroll_mode=False, gif_mode=False):
        if self._quitting:
            return
        self._capture_pending = False
        pixmap, virtual = ScreenGrabber.grab_full_desktop()
        if pixmap.isNull():
            self.show_notification("Capture error", "Screen capture unavailable. Check OS permissions; on Linux use an X11 session.")
            self._restore_when_idle()
            return
        overlay = CaptureOverlay(pixmap, virtual, self.config, multi_mode, ocr_mode)
        overlay.scroll_mode = scroll_mode
        overlay.gif_mode = gif_mode
        self._attach_overlay(overlay)

    def _attach_overlay(self, overlay):
        self.active_overlay = overlay
        overlay.destroyed.connect(lambda: self._overlay_closed(overlay))
        overlay.pinned_created.connect(self._keep_pinned_reference)
        overlay.notification_requested.connect(self.show_notification)
        overlay.multicapture_finished.connect(self._handle_multicapture_finished)
        overlay.scroll_capture_requested.connect(self._start_scroll_controller)
        overlay.gif_record_requested.connect(self._start_recorder_controller)
        overlay.ocr_requested.connect(self._run_ocr)
        overlay.show()
        overlay.activateWindow()
        overlay.raise_()

    def _overlay_closed(self, overlay):
        if self.active_overlay is overlay:
            self.active_overlay = None
        QTimer.singleShot(120, self._restore_when_idle)

    def _restore_when_idle(self):
        if (not self._quitting and self._restore_after_work and not self._capture_pending and
                self.active_overlay is None and self.active_scroll_ctrl is None and
                self.active_recorder_ctrl is None and not self._jobs):
            self._restore_after_work = False
            self.show_normal_window()

    def _submit_job(self, function, args, callback):
        job = ImageJob(function, *args)
        self._jobs.add(job)
        job.signals.result.connect(callback)
        job.signals.error.connect(lambda message: self.show_notification("Operation failed", message))
        job.signals.finished.connect(lambda: self._job_finished(job))
        QThreadPool.globalInstance().start(job)

    def _job_finished(self, job):
        self._jobs.discard(job)
        self._restore_when_idle()

    def _run_ocr(self, image):
        self.show_notification("Text grabber", "Reading text locally…")
        self._submit_job(extract_text, (image, self.config.ocr_language), self._show_ocr_result)

    def _show_ocr_result(self, text):
        if text:
            QApplication.clipboard().setText(text)
            self.show_notification("Text copied", f"{len(text)} characters copied to clipboard.")
        else:
            self.show_notification("Text grabber", "No readable text detected. Try a clearer or larger region.")
        dialog = OCRResultDialog(text or "No readable text detected.", None)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self._dialogs.remove(dialog) if dialog in self._dialogs else None)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _start_scroll_controller(self, target):
        controller = ScrollingCaptureController(target)
        self.active_scroll_ctrl = controller
        controller.finished.connect(self._handle_scroll_finished)
        controller.cancelled.connect(lambda: self.show_notification("Scroll capture", "Cancelled."))
        controller.destroyed.connect(lambda: self._scroll_closed(controller))
        # First frame and controller are shown only after the overlay has gone.

    def _scroll_closed(self, controller):
        if self.active_scroll_ctrl is controller:
            self.active_scroll_ctrl = None
        self._restore_when_idle()

    def _start_recorder_controller(self, target):
        controller = ScreenRecorderController(target)
        self.active_recorder_ctrl = controller
        controller.finished.connect(self._handle_recording_finished)
        controller.cancelled.connect(lambda: self.show_notification("Screen Recorder", "Recording cancelled."))
        controller.destroyed.connect(lambda: self._recorder_closed(controller))

    def _recorder_closed(self, controller):
        if self.active_recorder_ctrl is controller:
            self.active_recorder_ctrl = None
        self._restore_when_idle()

    def _handle_recording_finished(self, frames):
        if frames:
            self.show_notification("Screen Recorder", f"Encoding {len(frames)} frames into animated GIF…")
            self._submit_job(save_gif, (frames, self.config.save_directory, "SnapShot_Rec", 10),
                             self._on_gif_saved)

    def _on_gif_saved(self, filepath):
        self.show_notification("GIF Saved", f"Animation saved to {filepath.name}")
        try:
            QApplication.clipboard().setText(str(filepath))
        except Exception:
            pass

    def _handle_scroll_finished(self, frames):
        if frames:
            self.show_notification("Scrolling capture", "Aligning frames in the background…")
            self._submit_job(stitch_images, ([frame.toImage() for frame in frames], True),
                             lambda image: self._save_combined(image, "SnapShot_Scroll"))

    def _handle_multicapture_finished(self, crops):
        if crops:
            self.show_notification("Multi-snip", f"Combining {len(crops)} regions…")
            self._submit_job(stitch_images, ([crop.toImage() for crop in crops], False),
                             lambda image: self._save_combined(image, "SnapShot_Multi"))

    def _save_combined(self, image, prefix):
        try:
            path = save_image(image, self.config.save_directory, self.config.image_format, prefix)
        except (OSError, ValueError) as error:
            self.show_notification("Save failed", str(error))
            # Preserve the completed image for Copy, Save As, or another folder.
            self._restore_after_work = True
            self._open_editor(QPixmap.fromImage(image))
            return
        QApplication.clipboard().setImage(image)
        self.show_notification("Capture complete", f"{image.width()} × {image.height()} px • {path.name}")

    def _start_instant(self, split=False):
        if (self._capture_pending or self.active_overlay is not None or
                self.active_scroll_ctrl is not None or self.active_recorder_ctrl is not None):
            return
        self._capture_pending = True
        self._restore_after_work = self._restore_after_work or self.isVisible()
        self.hide()
        QTimer.singleShot(180, lambda: self._finish_instant(split))

    def _finish_instant(self, split):
        self._capture_pending = False
        if self._quitting:
            return
        try:
            shots = ScreenGrabber.grab_each_monitor() if split else [(ScreenGrabber.grab_full_desktop()[0], "Full")]
            if not shots or any(pixmap.isNull() for pixmap, _ in shots):
                raise RuntimeError("Unable to capture the screen. Check OS screen-recording permission.")
            QApplication.clipboard().setPixmap(shots[0][0])
            paths = [save_image(pixmap, self.config.save_directory, self.config.image_format,
                                f"SnapShot_{name}") for pixmap, name in shots]
            self.show_notification("Capture saved", f"{len(paths)} image(s) • {paths[0].parent}")
        except (OSError, ValueError, RuntimeError) as error:
            self.show_notification("Capture failed", str(error))
        self._restore_when_idle()

    def capture_all_monitors_split(self):
        self._start_instant(split=True)

    def capture_fullscreen_instant(self):
        self._start_instant()

    def start_delayed_capture(self, delay_ms=3000):
        if (self._capture_pending or self.active_overlay is not None or
                self.active_scroll_ctrl is not None or self.active_recorder_ctrl is not None):
            return
        self._restore_after_work = self._restore_after_work or self.isVisible()
        self._capture_pending = True
        self.hide()
        self.show_notification("Delayed capture", f"Select an area in {delay_ms // 1000} seconds…")
        QTimer.singleShot(delay_ms, self._do_launch_overlay)

    def _keep_pinned_reference(self, pin_win: PinnedScreenshotWindow) -> None:
        self.pinned_windows.append(pin_win)
        pin_win.destroyed.connect(
            lambda: self.pinned_windows.remove(pin_win) if pin_win in self.pinned_windows else None
        )

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config, None)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dlg.settings_saved.connect(self._on_settings_updated)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.exec()

    def _on_settings_updated(self) -> None:
        self.hotkey_manager.reload_hotkeys()
        self._register_window_shortcuts()
        self._refresh_labels()
        self._refresh_tray_menu_labels()

    def show_notification(self, title: str, message: str) -> None:
        self.status_label.setText(f"{title} • {message}")
        self.status_label.setToolTip(message)
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )

    def show_normal_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive
        )
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.show_notification("System tray unavailable", "Keep this window open to use the app.")
            return
        self.hide()
        self.show_notification("SnapShot Pro in Tray", "Press your capture hotkey anytime to capture!")

    def closeEvent(self, event) -> None:
        if self.tray_icon.isVisible():
            event.ignore()
            self.hide_to_tray()
        else:
            self.quit_application()

    def quit_application(self) -> None:
        self._quitting = True
        self.hotkey_manager.stop()
        if self.active_scroll_ctrl is not None:
            self.active_scroll_ctrl.cancel_capture()
        if self.active_recorder_ctrl is not None:
            self.active_recorder_ctrl.cancel_recording()
        if self.active_overlay is not None:
            self.active_overlay.close()
        for window in list(self.pinned_windows) + list(self._dialogs):
            window.close()
        QThreadPool.globalInstance().waitForDone(32000)
        self.tray_icon.hide()
        QApplication.quit()


# ============================================================================
# 13. APPLICATION ENTRY POINT
# ============================================================================

def main() -> None:
    if "--version" in sys.argv:
        print(f"SnapShot Pro {VERSION}")
        return
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("SnapShot Pro")
    app.setOrganizationName("SnapShotPro")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(get_app_icon())

    app.setApplicationVersion(VERSION)
    directory = pathlib.Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "SnapShot Pro", "SnapShot Pro is already running. Open it from the system tray.")
        return
    controller = SnapShotController()
    app.aboutToQuit.connect(controller.hotkey_manager.stop)
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(300, app.quit)
    if "--tray" not in sys.argv or not QSystemTrayIcon.isSystemTrayAvailable():
        controller.show()
    else:
        controller.show_notification("SnapShot Pro Ready", "Running in System Tray.")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
