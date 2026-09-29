"""Dựng PDF / ảnh mẫu cho test upload (thuần hàm, không phải fixture)."""

import io

from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject


def simple_pdf(pages: int = 1) -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for n in range(pages):
        pdf.add_page()
        pdf.cell(text=f"Trang {n + 1}")
    return bytes(pdf.output())


def _writer(pages: int = 1) -> PdfWriter:
    return PdfWriter(clone_from=PdfReader(io.BytesIO(simple_pdf(pages))))


def _dump(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def encrypted_pdf() -> bytes:
    writer = _writer()
    writer.encrypt("secret")
    return _dump(writer)


def javascript_pdf() -> bytes:
    writer = _writer()
    action = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"),
                               NameObject("/JS"): TextStringObject("app.alert('x')")})
    writer.root_object[NameObject("/OpenAction")] = action
    return _dump(writer)


def attachment_pdf() -> bytes:
    writer = _writer()
    writer.add_attachment("ghi-chu.txt", b"noi dung")
    return _dump(writer)


def launch_pdf() -> bytes:
    writer = _writer()
    action = DictionaryObject({NameObject("/S"): NameObject("/Launch"), NameObject("/F"): TextStringObject("calc.exe")})
    writer.root_object[NameObject("/OpenAction")] = action
    return _dump(writer)


def richmedia_pdf() -> bytes:
    writer = _writer()
    annotation = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/RichMedia"),
        NameObject("/Rect"): ArrayObject([]),
    })
    writer.pages[0][NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    return _dump(writer)


def jpeg_bytes(size=(100, 50), orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, "red")
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def png_bytes(size=(20, 20), mode="RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size).save(buffer, "PNG")
    return buffer.getvalue()
