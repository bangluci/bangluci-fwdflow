"""Đưa chứng từ về ảnh chuẩn cho Claude: PDF → tối đa 10 trang 200 dpi, ảnh → xoay theo EXIF, cạnh dài ≤ 2576px."""

import io
from pathlib import Path

import pypdfium2
from PIL import Image, ImageOps

MAX_PAGES = 10
DEFAULT_DPI = 200
MAX_SIDE = 2576
JPEG_QUALITY = 85


def normalize_image(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as img:
        page = ImageOps.exif_transpose(img).convert("RGB")
    page.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    page.save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def _render_page(pdf: pypdfium2.PdfDocument, index: int, dpi: int) -> bytes:
    buffer = io.BytesIO()
    pdf[index].render(scale=dpi / 72).to_pil().convert("RGB").save(buffer, "JPEG", quality=95)
    return normalize_image(buffer.getvalue())


def render_pdf_pages(path: Path, max_pages: int = MAX_PAGES, dpi: int = DEFAULT_DPI) -> list[bytes]:
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        return [_render_page(pdf, index, dpi) for index in range(min(len(pdf), max_pages))]
    finally:
        pdf.close()


def render_page(path: Path, mime: str, page: int) -> bytes | None:
    """Ảnh của một trang (đánh số từ 1) đúng như AI thấy; ngoài khoảng thì None. Không render cả tài liệu."""
    if mime != "application/pdf":
        return normalize_image(path.read_bytes()) if page == 1 else None
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        return _render_page(pdf, page - 1, DEFAULT_DPI) if 1 <= page <= min(len(pdf), MAX_PAGES) else None
    finally:
        pdf.close()


def render_document(path: Path, mime: str, max_pages: int = MAX_PAGES) -> list[bytes]:
    """Các ảnh đúng như AI sẽ thấy (cũng là ảnh trang cho màn duyệt)."""
    if mime == "application/pdf":
        return render_pdf_pages(path, max_pages)
    return [normalize_image(path.read_bytes())]
