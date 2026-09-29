import io

import pytest
from pypdf import PdfReader

from app.config import Settings, get_settings
from app.lastmile.label_pdf import track_url

BASE = "https://demo.example"
A6_POINTS = (297.6, 419.5)


@pytest.fixture
def order(db, make_shipment, make_last_mile_order, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_base_url", BASE + "/")
    shipment = make_shipment(status="AT_WAREHOUSE", total_packages=20)
    return make_last_mile_order(shipment, 3, tracking_code="DEM00TRACK", weight_kg=12.5)


def _pdf(client, order):
    res = client.get(f"/api/last-mile-orders/{order.id}/label.pdf")
    assert res.status_code == 200
    return res, PdfReader(io.BytesIO(res.content))


def test_label_pdf_is_single_a6_page(client, login_as, order):
    login_as("DISPATCH")
    res, reader = _pdf(client, order)
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"] == 'attachment; filename="nhan-DEM00TRACK.pdf"'
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert (round(float(box.width), 1), round(float(box.height), 1)) == pytest.approx(A6_POINTS, abs=0.6)


def test_label_pdf_has_code_and_track_url_text(client, login_as, order):
    login_as("DISPATCH")
    text = _pdf(client, order)[1].pages[0].extract_text()
    assert "DEM00-TRACK" in text and "https://demo.example/track/DEM00TRACK" in text
    assert "Nguyễn Văn An" in text and "3 kiện" in text and "12.5 kg" in text


def test_track_url_joins_base_without_double_slash():
    assert track_url("ABCDE12345", "https://x.test/") == "https://x.test/track/ABCDE12345"
    assert track_url("ABCDE12345", "https://x.test") == "https://x.test/track/ABCDE12345"


@pytest.mark.parametrize(("role", "status"), [("DOCS", 403), ("DRIVER", 403), ("DISPATCH", 200)])
def test_label_requires_dispatch_role(client, login_as, order, role, status):
    login_as(role)
    assert client.get(f"/api/last-mile-orders/{order.id}/label.pdf").status_code == status


def test_label_unknown_order_404(client, login_as):
    login_as("DISPATCH")
    assert client.get("/api/last-mile-orders/999999/label.pdf").status_code == 404


def test_prod_requires_https_public_base_url():
    with pytest.raises(ValueError, match="https"):
        Settings(app_env="prod", public_base_url="http://demo.example")
    assert Settings(app_env="prod", public_base_url="https://demo.example").public_base_url.startswith("https")
