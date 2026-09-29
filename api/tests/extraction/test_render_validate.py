import io
from datetime import date

from PIL import Image

from app.ai.extraction.render import normalize_image, render_document, render_pdf_pages
from app.ai.extraction.validate import validate_fields
from tests.documents import pdf_factory as factory

TODAY = date(2026, 10, 1)


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def _bl(**overrides) -> dict:
    data = {"onboard_date": "2026-09-20", "total_packages": 10, "gross_weight_kg": "1000.5",
            "containers": [{"container_no": "CSQU3054383", "seal_no": "S1", "container_type_raw": "45G1",
                            "container_type": "40HC", "packages": 10, "gross_weight_kg": "1000.5"}]}
    return {**data, **overrides}


def _codes(issues):
    return {(i.path, i.code, i.level) for i in issues}


def test_render_caps_at_10_pages(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(factory.simple_pdf(12))
    assert len(render_pdf_pages(path)) == 10


def test_render_document_image_returns_single_jpeg(tmp_path):
    path = tmp_path / "a.jpg"
    path.write_bytes(factory.jpeg_bytes((300, 200)))
    pages = render_document(path, "image/jpeg")
    assert len(pages) == 1 and _open(pages[0]).format == "JPEG"


def test_normalize_image_long_side_2576_jpeg():
    out = _open(normalize_image(factory.png_bytes((5000, 3000))))
    assert out.format == "JPEG" and max(out.size) == 2576


def test_normalize_image_applies_exif_rotation():
    assert _open(normalize_image(factory.jpeg_bytes((100, 50), orientation=6))).size == (50, 100)


def test_valid_document_has_no_issues():
    assert validate_fields("HBL", _bl(), pages=2, today=TODAY) == []


def test_check_digit_issue_is_block():
    data = _bl()
    data["containers"][0]["container_no"] = "CSQU3054384"
    assert ("/containers/0/container_no", "CHECK_DIGIT", "BLOCK") in _codes(validate_fields("HBL", data, 1, TODAY))


def test_negative_weight_is_block():
    data = _bl(gross_weight_kg="-5")
    data["containers"][0]["packages"] = -1
    assert {("/gross_weight_kg", "NEGATIVE", "BLOCK"), ("/containers/0/packages", "NEGATIVE", "BLOCK")} <= \
        _codes(validate_fields("HBL", data, 1, TODAY))


def test_invoice_negative_line_amount_is_block():
    data = {"invoice_date": "2026-09-01", "total_amount": "100", "lines": [{"quantity": "1", "unit_price": "5",
                                                                           "amount": "-5"}]}
    assert ("/lines/0/amount", "NEGATIVE", "BLOCK") in _codes(validate_fields("INVOICE", data, 1, TODAY))


def test_date_out_of_range_is_block():
    assert ("/onboard_date", "DATE_OUT_OF_RANGE", "BLOCK") in _codes(
        validate_fields("HBL", _bl(onboard_date="2019-01-01"), 1, TODAY))
    assert ("/onboard_date", "DATE_OUT_OF_RANGE", "BLOCK") in _codes(
        validate_fields("HBL", _bl(onboard_date="2028-01-01"), 1, TODAY))


def test_container_type_45g1_maps_40hc():
    assert validate_fields("HBL", _bl(), 1, TODAY) == []
    data = _bl()
    data["containers"][0]["container_type"] = "40GP"
    assert ("/containers/0/container_type", "CONTAINER_TYPE_MISMATCH", "BLOCK") in _codes(
        validate_fields("HBL", data, 1, TODAY))


def test_container_type_raw_with_punctuation_is_normalized():
    data = _bl()
    data["containers"][0].update(container_type_raw="40'HC", container_type="40HC")
    assert validate_fields("HBL", data, 1, TODAY) == []


def test_container_type_unmapped_is_block():
    data = _bl()
    data["containers"][0].update(container_type_raw="53FT", container_type=None)
    assert ("/containers/0/container_type", "CONTAINER_TYPE_UNMAPPED", "BLOCK") in _codes(
        validate_fields("HBL", data, 1, TODAY))
    data["containers"][0].update(container_type_raw="45G1", container_type=None)
    assert ("/containers/0/container_type", "CONTAINER_TYPE_UNMAPPED", "BLOCK") in _codes(
        validate_fields("HBL", data, 1, TODAY))


def test_pages_truncated_is_warn():
    assert ("/pages", "PAGES_TRUNCATED", "WARN") in _codes(validate_fields("HBL", _bl(), 12, TODAY))
    assert validate_fields("HBL", _bl(), 10, TODAY) == []
