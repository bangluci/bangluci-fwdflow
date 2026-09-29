import pytest
from PIL import Image

from app.documents.sanitize import check_pdf, clean_image, sniff_mime
from app.envelope import AppError
from tests.documents import pdf_factory as factory


def _write(tmp_path, data: bytes, name="f.bin"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _code(callable_, *args):
    with pytest.raises(AppError) as err:
        callable_(*args)
    assert err.value.message and err.value.status == 400
    return err.value.code


def test_sniff_mime_known_types():
    assert sniff_mime(b"%PDF-1.7 ...") == "application/pdf"
    assert sniff_mime(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert sniff_mime(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert sniff_mime(b"MZ\x90\x00") is None


def test_check_pdf_counts_pages(tmp_path):
    assert check_pdf(_write(tmp_path, factory.simple_pdf(3))) == 3


def test_check_pdf_accepts_20_pages(tmp_path):
    assert check_pdf(_write(tmp_path, factory.simple_pdf(20))) == 20


def test_check_pdf_rejects_21_pages(tmp_path):
    assert _code(check_pdf, _write(tmp_path, factory.simple_pdf(21))) == "PDF_TOO_MANY_PAGES"


def test_check_pdf_rejects_encrypted(tmp_path):
    assert _code(check_pdf, _write(tmp_path, factory.encrypted_pdf())) == "PDF_ENCRYPTED"


@pytest.mark.parametrize("build", [factory.javascript_pdf, factory.launch_pdf, factory.attachment_pdf,
                                   factory.richmedia_pdf], ids=["javascript", "launch", "embedded", "richmedia"])
def test_check_pdf_rejects_active_content(tmp_path, build):
    assert _code(check_pdf, _write(tmp_path, build())) == "PDF_ACTIVE_CONTENT"


def test_check_pdf_rejects_garbage(tmp_path):
    assert _code(check_pdf, _write(tmp_path, b"%PDF-1.4 khong phai pdf that")) == "PDF_INVALID"


def test_clean_image_drops_exif_and_rotates(tmp_path):
    src = _write(tmp_path, factory.jpeg_bytes((100, 50), orientation=6), "a.jpg")
    dst = tmp_path / "out.jpg"
    clean_image(src, dst)
    with Image.open(dst) as out:
        assert out.size == (50, 100) and len(out.getexif()) == 0


def test_clean_image_rejects_over_40_megapixels(tmp_path):
    src = _write(tmp_path, factory.png_bytes((7000, 6000), mode="1"), "big.png")
    assert _code(clean_image, src, tmp_path / "o.jpg") == "IMAGE_TOO_LARGE"


def test_clean_image_rejects_side_over_8000(tmp_path):
    src = _write(tmp_path, factory.png_bytes((8001, 10)), "long.png")
    assert _code(clean_image, src, tmp_path / "o.jpg") == "IMAGE_TOO_LARGE"


def test_clean_image_rejects_invalid_bytes(tmp_path):
    src = _write(tmp_path, b"\x89PNG\r\n\x1a\nkhong-phai-anh", "bad.png")
    assert _code(clean_image, src, tmp_path / "o.jpg") == "IMAGE_INVALID"
