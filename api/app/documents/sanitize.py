"""Làm sạch file upload: xác minh loại bằng magic bytes, từ chối PDF nguy hiểm, re-encode ảnh bỏ EXIF."""

import logging
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

from app.envelope import AppError

log = logging.getLogger("fwdflow.upload")

MAX_PDF_PAGES = 20
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_SIDE = 8000
ACTIVE_CONTENT_NAMES = frozenset({"/JavaScript", "/JS", "/Launch", "/EmbeddedFiles", "/RichMedia"})

_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def sniff_mime(head: bytes) -> str | None:
    for signature, mime in _SIGNATURES:
        if head.startswith(signature):
            return mime
    return None


def _has_active_content(reader: PdfReader) -> bool:
    """Duyệt đồ thị object từ trailer, tìm tên nguy hiểm ở key hoặc giá trị."""
    seen: set[tuple[int, int]] = set()
    stack: list = [reader.trailer]
    while stack:
        obj = stack.pop()
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in seen:
                continue
            seen.add(key)
            obj = obj.get_object()
        if isinstance(obj, DictionaryObject):
            for key, value in obj.items():
                if key in ACTIVE_CONTENT_NAMES or (isinstance(value, NameObject) and value in ACTIVE_CONTENT_NAMES):
                    return True
                stack.append(value)
        elif isinstance(obj, ArrayObject):
            stack.extend(obj)
        elif isinstance(obj, NameObject) and obj in ACTIVE_CONTENT_NAMES:
            return True
    return False


def check_pdf(path: Path) -> int:
    """Trả về số trang; ném AppError nếu PDF mã hoá, quá 20 trang, có nội dung chủ động hoặc hỏng."""
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            raise AppError("PDF_ENCRYPTED", "PDF có mật khẩu, hãy gửi bản không mã hoá", 400)
        pages = len(reader.pages)
        if pages > MAX_PDF_PAGES:
            raise AppError("PDF_TOO_MANY_PAGES", f"PDF quá {MAX_PDF_PAGES} trang", 400)
        if _has_active_content(reader):
            raise AppError("PDF_ACTIVE_CONTENT", "PDF chứa JavaScript / file đính kèm / lệnh chạy, không nhận", 400)
        return pages
    except AppError:
        raise
    except Exception as exc:
        log.warning("PDF không đọc được: %s", exc, exc_info=True)
        raise AppError("PDF_INVALID", "Không đọc được file PDF", 400) from exc


def clean_image(src: Path, dst: Path) -> None:
    """Đọc kích thước từ header trước khi giải mã; xoay theo EXIF rồi lưu JPEG q90 không kèm metadata."""
    try:
        with Image.open(src) as img:
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS or max(width, height) > MAX_IMAGE_SIDE:
                raise AppError("IMAGE_TOO_LARGE", "Ảnh quá lớn (tối đa 40 triệu điểm ảnh, cạnh ≤ 8000px)", 400)
            cleaned = ImageOps.exif_transpose(img).convert("RGB")
            cleaned.save(dst, "JPEG", quality=90)
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        log.warning("Ảnh không đọc được: %s", exc, exc_info=True)
        raise AppError("IMAGE_INVALID", "Không đọc được file ảnh", 400) from exc
