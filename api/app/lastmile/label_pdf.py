"""Nhãn giao hàng A6 dọc có mã vận đơn và mã QR trỏ tới trang tra cứu công khai (font DejaVu để có dấu tiếng Việt)."""

import io
from pathlib import Path

import segno
from fpdf import FPDF

from app.lastmile.models import LastMileOrder
from app.lastmile.tracking_code import format_code

FONT_DIR = Path(__file__).parent / "fonts"
QR_SIZE_MM = 40
PAGE_MM = (105, 148)  # A6 dọc
MARGIN_MM = 8


def track_url(code: str, base_url: str) -> str:
    """Nối `/track/<mã>` vào địa chỉ gốc mà không sinh `//` thừa."""
    return f"{base_url.rstrip('/')}/track/{code}"


def _qr_png(url: str) -> io.BytesIO:
    buffer = io.BytesIO()
    segno.make(url, error="m").save(buffer, kind="png", scale=8, border=1)
    buffer.seek(0)
    return buffer


def render_label_pdf(order: LastMileOrder, shipment_code: str, base_url: str) -> bytes:
    url = track_url(order.tracking_code, base_url)
    pdf = FPDF(format=PAGE_MM, unit="mm")
    pdf.set_auto_page_break(False)
    pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
    pdf.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    width = PAGE_MM[0] - 2 * MARGIN_MM

    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(width, 6, "FwdFlow", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "B", 20)
    pdf.cell(width, 11, format_code(order.tracking_code), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.image(_qr_png(url), x=(PAGE_MM[0] - QR_SIZE_MM) / 2, y=pdf.get_y() + 1, w=QR_SIZE_MM, h=QR_SIZE_MM)
    pdf.set_y(pdf.get_y() + QR_SIZE_MM + 3)
    pdf.set_font("DejaVu", "", 7)
    pdf.multi_cell(width, 3.5, url, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("DejaVu", "B", 11)
    pdf.multi_cell(width, 5.5, order.recipient_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(width, 5.5, order.recipient_phone, new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(width, 5, order.address, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    weight = f" · {order.weight_kg:g} kg" if order.weight_kg is not None else ""
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(width, 5.5, f"{order.packages} kiện{weight}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 8)
    pdf.cell(width, 4.5, f"Lô {shipment_code} · giao ngày {order.planned_date:%d/%m/%Y}", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
