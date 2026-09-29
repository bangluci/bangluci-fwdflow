"""Kết quả trích xuất mẫu (đã chuẩn hoá như `model_dump(mode="json")` của schema) cho các test."""

from app.ai.extraction.schemas import BLExtract, InvoiceExtract, PackingListExtract

BASE = {"legible": True, "suspicious_content": False, "suspicious_note": None}


def bl(**overrides) -> BLExtract:
    data = {
        **BASE, "detected_doc_type": "HBL", "bl_no": "HBL001", "carrier_name": "MAERSK", "shipper": "ABC CO",
        "consignee": "CONG TY TNHH MINH LONG", "notify_party": None, "vessel": "EVER A", "voyage": "12E",
        "pol": "CNSHA", "pod": "VNSGN", "onboard_date": "2026-09-20", "total_packages": 100, "package_unit": "CTNS",
        "gross_weight_kg": "1000.50",
        "containers": [{"container_no": "CSQU3054383", "seal_no": "S1", "container_type_raw": "45G1",
                        "container_type": "40HC", "packages": 100, "gross_weight_kg": "1000.50"}],
    }
    return BLExtract.model_validate({**data, **overrides})


def invoice(**overrides) -> InvoiceExtract:
    data = {
        **BASE, "detected_doc_type": "INVOICE", "invoice_no": "INV-1", "invoice_date": "2026-09-01",
        "seller": "ABC CO", "buyer": "MINH LONG CO., LTD", "currency": "USD", "incoterm": "FOB",
        "total_amount": "1500.50",
        "lines": [{"description": "Vải cotton", "quantity": "100", "unit": "M", "unit_price": "10.005",
                   "amount": "1000.50"}, {"description": "Chỉ may", "quantity": "50", "unit": "CONE",
                                          "unit_price": "10", "amount": "500"}],
    }
    return InvoiceExtract.model_validate({**data, **overrides})


def packing_list(**overrides) -> PackingListExtract:
    data = {
        **BASE, "detected_doc_type": "PACKING_LIST", "packing_list_no": "PL-1", "date": "2026-09-01",
        "total_packages": 100, "total_gross_weight_kg": "1000.50", "total_net_weight_kg": "950.00",
        "lines": [{"description": "Vải cotton", "packages": 100, "quantity": "100", "unit": "M",
                   "gross_weight_kg": "1000.50", "net_weight_kg": "950.00"}],
        "containers": [{"container_no": "CSQU3054383", "seal_no": "S1"}],
    }
    return PackingListExtract.model_validate({**data, **overrides})


def dump(extract) -> dict:
    return extract.model_dump(mode="json")
