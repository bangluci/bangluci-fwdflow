import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image

from app.config import get_settings
from app.documents.storage import path_for, save_photo
from app.envelope import AppError
from tests.documents.pdf_factory import simple_pdf


class FakeUpload:
    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


def _jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (40, 30), "blue")
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def _stored_files() -> list[Path]:
    root = get_settings().files_dir
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_save_photo_reencodes_jpeg_and_names_file_by_sha256():
    stored = save_photo(FakeUpload(_jpeg_with_exif()))
    data = path_for(stored.sha256).read_bytes()
    assert hashlib.sha256(data).hexdigest() == stored.sha256 and stored.mime == "image/jpeg"
    assert len(Image.open(io.BytesIO(data)).getexif()) == 0


def test_save_photo_png_becomes_jpeg():
    buffer = io.BytesIO()
    Image.new("RGBA", (20, 20), (255, 0, 0, 128)).save(buffer, "PNG")
    stored = save_photo(FakeUpload(buffer.getvalue()))
    assert stored.mime == "image/jpeg" and Image.open(path_for(stored.sha256)).format == "JPEG"


def test_save_photo_rejects_pdf_before_saving_400():
    with pytest.raises(AppError) as info:
        save_photo(FakeUpload(simple_pdf()))
    assert (info.value.code, info.value.status) == ("PHOTO_MUST_BE_IMAGE", 400) and _stored_files() == []


def test_save_photo_rejects_garbage_400():
    with pytest.raises(AppError) as info:
        save_photo(FakeUpload(b"khong phai anh"))
    assert (info.value.code, info.value.status) == ("UNSUPPORTED_FILE_TYPE", 400)
