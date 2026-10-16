"""Small, lazy-loaded image/OCR jobs. No network calls or import-time setup."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

VERSION = "1.1.0"
MAX_IMAGE_PIXELS = 48_000_000


def image_to_pil(image: QImage):
    from PIL import Image
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes("RGBA", (image.width(), image.height()),
                           image.constBits().asstring(image.sizeInBytes()),
                           "raw", "RGBA", image.bytesPerLine()).convert("RGB")


def pil_to_image(image) -> QImage:
    image = image.convert("RGB")
    return QImage(image.tobytes(), image.width, image.height, image.width * 3,
                  QImage.Format.Format_RGB888).copy()


def physical_rect(rect, scale: float):
    """Convert logical edges rather than independently rounding width/height."""
    from PyQt6.QtCore import QRect
    left, top = round(rect.x() * scale), round(rect.y() * scale)
    right = round((rect.x() + rect.width()) * scale)
    bottom = round((rect.y() + rect.height()) * scale)
    return QRect(left, top, right - left, bottom - top)


def crop_pixmap(pixmap: QPixmap, logical_rect) -> QPixmap:
    rect = physical_rect(logical_rect, pixmap.devicePixelRatio()).intersected(pixmap.rect())
    if rect.isEmpty():
        return QPixmap()
    cropped = pixmap.copy(rect)
    cropped.setDevicePixelRatio(pixmap.devicePixelRatio())
    return cropped


def _overlap(previous, current) -> int:
    """Find downward scroll overlap, verifying normalized full-overlap error.

    Search every row (including odd offsets), not just the first 500 pixels.
    A narrow anchor makes searching cheap; full strips reject false matches.
    Flat images have no reliable alignment and are appended without trimming.
    """
    from PIL import Image, ImageChops, ImageStat
    if previous.width != current.width or min(previous.height, current.height) < 48:
        return 0
    width = min(64, current.width)
    a = previous.convert("L").resize((width, previous.height), Image.Resampling.BOX)
    b = current.convert("L").resize((width, current.height), Image.Resampling.BOX)
    if ImageStat.Stat(b).stddev[0] < 3:
        return 0
    anchor_height = 24
    # A page often begins with blank whitespace. Anchor on a textured strip,
    # otherwise dozens of blank rows tie for "best" and hide the real match.
    anchor_y = max(range(0, min(512, b.height - anchor_height) + 1, 8),
                   key=lambda y: ImageStat.Stat(b.crop((0, y, width, y + anchor_height))).stddev[0])
    anchor = b.crop((0, anchor_y, width, anchor_y + anchor_height))
    candidates = []
    for offset in range(max(0, a.height - b.height), a.height - anchor_y - anchor_height + 1):
        probe = a.crop((0, offset + anchor_y, width, offset + anchor_y + anchor_height))
        error = ImageStat.Stat(ImageChops.difference(probe, anchor)).rms[0]
        candidates.append((error, offset))
    candidates.sort()
    verified = []
    for _, offset in candidates[:16]:
        overlap = min(a.height - offset, b.height)
        diff = ImageChops.difference(a.crop((0, offset, width, offset + overlap)),
                                     b.crop((0, 0, width, overlap)))
        verified.append((ImageStat.Stat(diff).rms[0], overlap))
    if not verified:
        return 0
    error, overlap = min(verified, key=lambda value: (value[0], -value[1]))
    return overlap if error <= 6 else 0


def stitch_images(images: list[QImage], detect_overlap: bool = True) -> QImage:
    """Join images once after alignment; independent snips never lose pixels."""
    from PIL import Image, ImageChops
    if not images:
        raise ValueError("No frames to combine.")
    if any(image.isNull() for image in images):
        raise ValueError("A captured frame is empty.")
    if sum(image.width() * image.height() for image in images) > MAX_IMAGE_PIXELS:
        raise ValueError("Capture limit reached (48 megapixels). Finish a shorter capture.")
    parts = []
    previous = None
    for image in images:
        current = image_to_pil(image)
        if detect_overlap and previous is not None and current.size == previous.size:
            if ImageChops.difference(previous, current).getbbox() is None:
                continue
        overlap = _overlap(previous, current) if detect_overlap and previous is not None else 0
        parts.append(current.crop((0, overlap, current.width, current.height)))
        previous = current
    width = max(image.width for image in parts)
    height = sum(image.height for image in parts)
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("Combined image exceeds 48 megapixels. Use fewer snips.")
    result = Image.new("RGB", (width, height), "white")
    y = 0
    for image in parts:
        result.paste(image, (0, y))
        y += image.height
    return pil_to_image(result)


def save_image(image: QImage | QPixmap, directory: str, fmt: str = "PNG",
               prefix: str = "SnapShot", path: str | None = None) -> pathlib.Path:
    """Atomic save. Failures leave the editor open and never report success."""
    if image.isNull():
        raise ValueError("Select an area before saving.")
    fmt = fmt.upper()
    fmt = {"JPEG": "JPG"}.get(fmt, fmt)
    if fmt not in {"PNG", "JPG", "WEBP"}:
        raise ValueError("Choose PNG, JPG, or WEBP.")
    extension = {"PNG": "png", "JPG": "jpg", "WEBP": "webp"}[fmt]
    target = pathlib.Path(path).expanduser() if path else pathlib.Path(directory).expanduser() / (
        f"{prefix}_{datetime.now():%Y-%m-%d_%H-%M-%S-%f}_{uuid.uuid4().hex[:4]}.{extension}"
    )
    if not target.suffix:
        target = target.with_suffix("." + extension)
    if path and target.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Use a .png, .jpg, .jpeg, or .webp filename.")
    if path:
        fmt = {".png": "PNG", ".jpg": "JPG", ".jpeg": "JPG", ".webp": "WEBP"}[target.suffix.lower()]
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", suffix="." + extension, dir=target.parent)
    os.close(fd)
    try:
        if not image.save(temporary, fmt, 95):
            raise OSError(f"Could not encode {fmt} image. Check the image plugin and free disk space.")
        os.replace(temporary, target)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)
    return target


def find_tesseract() -> str | None:
    configured = os.environ.get("SNAPSHOT_TESSERACT")
    if configured and pathlib.Path(configured).is_file():
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    for directory in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                      os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                      str(pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs")):
        candidate = pathlib.Path(directory) / "Tesseract-OCR" / "tesseract.exe"
        if candidate.is_file():
            return str(candidate)
    for candidate in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"):
        if pathlib.Path(candidate).is_file():
            return candidate
    return None


def extract_text(image: QImage, language: str = "eng") -> str:
    from PyQt6.QtCore import QBuffer, QIODevice
    executable = find_tesseract()
    if not executable:
        raise RuntimeError("Install Tesseract OCR to use Text Grabber. See README for your platform. "
                           "The rest of SnapShot Pro works without OCR.")
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    result = subprocess.run([executable, "stdin", "stdout", "-l", language],
                            input=bytes(buffer.data()), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30,
                            creationflags=0x08000000 if os.name == "nt" else 0)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "OCR failed.")
    return result.stdout.decode("utf-8", "replace").strip()


class JobSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class ImageJob(QRunnable):
    def __init__(self, function, *args):
        super().__init__()
        self.function, self.args = function, args
        self.signals = JobSignals()

    def run(self):
        try:
            self.signals.result.emit(self.function(*self.args))
        except Exception as error:
            self.signals.error.emit(str(error))
        finally:
            self.signals.finished.emit()
