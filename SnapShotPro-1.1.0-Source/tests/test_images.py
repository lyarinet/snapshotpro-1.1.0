import random
import shutil
import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from snapshot_core import (crop_pixmap, physical_rect, pil_to_image, image_to_pil,
                           stitch_images, save_image, extract_text)

def patterned_image(width=120, height=2500):
    from PIL import Image
    rng = random.Random(42)
    return Image.frombytes('RGB', (width, height), rng.randbytes(width * height * 3))

def test_raw_image_conversion_preserves_pixels_and_stride(app):
    image = QImage(17, 9, QImage.Format.Format_RGB888)
    image.fill(QColor('#124578'))
    result = pil_to_image(image_to_pil(image))
    assert result.size() == image.size()
    assert result.pixelColor(16, 8).name() == '#124578'

def test_hidpi_crop_preserves_native_resolution(app):
    image = QPixmap(800, 600)
    image.fill(QColor('red'))
    image.setDevicePixelRatio(2)
    crop = crop_pixmap(image, QRect(20, 30, 120, 80))
    assert (crop.width(), crop.height()) == (240, 160)
    assert crop.devicePixelRatio() == 2
    assert crop.toImage().pixelColor(239, 159) == QColor('red')
    assert physical_rect(QRect(3, 2, 19, 7), 1.5) == QRect(4, 3, 29, 11)

def test_scroll_overlap_over_500_and_odd_offset(app):
    image = patterned_image()
    frames = [pil_to_image(image.crop((0, y, 120, y + 1000))) for y in (0, 317, 634)]
    stitched = image_to_pil(stitch_images(frames))
    assert stitched.size == (120, 1634)
    assert stitched.tobytes() == image.crop((0, 0, 120, 1634)).tobytes()

def test_duplicate_scroll_frames_are_removed(app):
    image = pil_to_image(patterned_image(80, 180))
    result = stitch_images([image, image, image])
    assert result.size() == image.size()

def test_scroll_alignment_with_blank_top_margin_and_real_text(app):
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (400, 2300), 'white')
    draw = ImageDraw.Draw(image)
    for number, y in enumerate(range(90, 2300, 300)):
        draw.text((20, y), f'SNAP number {number} - distinct page content', fill='black')
        draw.rectangle((20, y+30, 250+number*10, y+45), fill=(20+number*20, 60, 110))
    frames = [pil_to_image(image.crop((0, y, 400, y+900))) for y in (0, 151, 302)]
    result = image_to_pil(stitch_images(frames))
    assert result.size == (400, 1202)
    assert result.tobytes() == image.crop((0, 0, 400, 1202)).tobytes()

def test_independent_snips_are_never_overlap_trimmed(app):
    a = QImage(80, 30, QImage.Format.Format_RGB32); a.fill(QColor('red'))
    b = QImage(45, 25, QImage.Format.Format_RGB32); b.fill(QColor('blue'))
    result = stitch_images([a, b], detect_overlap=False)
    assert (result.width(), result.height()) == (80, 55)
    assert result.pixelColor(1, 29) == QColor('red')
    assert result.pixelColor(1, 30) == QColor('blue')
    assert result.pixelColor(79, 54) == QColor('white')
    assert stitch_images([a, a], False).height() == 60

def test_unrelated_images_are_appended_without_data_loss(app):
    a = pil_to_image(patterned_image(100, 240))
    b = QImage(100, 180, QImage.Format.Format_RGB32); b.fill(QColor('white'))
    assert stitch_images([a, b]).height() == 420

@pytest.mark.parametrize('fmt', ['PNG', 'JPG', 'WEBP'])
def test_atomic_save_format_and_unique_names(app, tmp_path, fmt):
    image = QImage(32, 24, QImage.Format.Format_RGB32); image.fill(QColor('#32acbd'))
    first = save_image(image, str(tmp_path), fmt)
    second = save_image(image, str(tmp_path), fmt)
    assert first != second
    assert QImage(str(first)).size() == image.size()
    assert not list(tmp_path.glob('.snapshot-*'))

def test_failed_save_leaves_no_partial_files(app, tmp_path):
    image = QImage(32, 24, QImage.Format.Format_RGB32); image.fill(QColor('red'))
    blocker = tmp_path / 'file'; blocker.write_text('keep')
    with pytest.raises(OSError):
        save_image(image, str(blocker))
    assert blocker.read_text() == 'keep'
    with pytest.raises(ValueError):
        save_image(QImage(), str(tmp_path))

def test_save_as_uses_extension_or_selected_format(app, tmp_path):
    image = QImage(16, 12, QImage.Format.Format_RGB32); image.fill(QColor('green'))
    saved = save_image(image, str(tmp_path), 'WEBP', path=str(tmp_path / 'chosen'))
    assert saved.suffix == '.webp'
    saved = save_image(image, str(tmp_path), 'PNG', path=str(tmp_path / 'chosen.jpg'))
    assert saved.read_bytes().startswith(b'\xff\xd8')

def test_real_local_ocr(app):
    if not shutil.which('tesseract'):
        pytest.skip('Tesseract is optional')
    image = QImage(900, 160, QImage.Format.Format_RGB32); image.fill(QColor('white'))
    painter = QPainter(image); painter.setPen(QColor('black'))
    painter.setFont(QFont('DejaVu Sans', 40))
    painter.drawText(25, 100, 'SNAPSHOT PRO 12345'); painter.end()
    text = extract_text(image)
    assert 'SNAPSHOT' in text.upper()
    assert '12345' in text

def test_missing_ocr_is_actionable(app, monkeypatch):
    monkeypatch.setattr('snapshot_core.find_tesseract', lambda: None)
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    with pytest.raises(RuntimeError, match='Install Tesseract'):
        extract_text(image)
