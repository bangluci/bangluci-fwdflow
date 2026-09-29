"""Cột được phép vào audit của module lô (không có cột bí mật hay PII)."""

from app.audit.service import register_audit_fields

SHIPMENT_FIELDS = (
    "code", "load_type", "delivery_mode", "customer_id", "staff_id", "carrier_id", "pol_port_id", "pod_port_id",
    "dest_warehouse_id", "mbl_no", "hbl_no", "vessel", "voyage", "etd", "eta", "claims_fta", "do_no",
    "do_valid_until", "total_packages", "version", "status",
)
ITEM_FIELDS = ("shipment_id", "line_no", "description", "quantity", "unit", "packages", "gross_weight_kg",
               "value_amount", "value_currency", "hs_code", "hs_source")
DECLARATION_FIELDS = ("shipment_id", "declaration_no", "type_code", "registered_at", "lane", "cleared_at")
CONTAINER_FIELDS = ("shipment_id", "container_no", "container_type", "seal_no", "gross_weight_kg", "status")
SHIPMENT_EVENT_FIELDS = ("kind", "occurred_at", "from_status", "to_status", "adjusts_event_id", "reason")
CONTAINER_EVENT_FIELDS = ("kind", "occurred_at", "adjusts_event_id", "reason")

register_audit_fields("shipment", SHIPMENT_FIELDS)
register_audit_fields("shipment_item", ITEM_FIELDS)
register_audit_fields("customs_declaration", DECLARATION_FIELDS)
register_audit_fields("container", CONTAINER_FIELDS)
register_audit_fields("shipment_event", SHIPMENT_EVENT_FIELDS)
register_audit_fields("container_event", CONTAINER_EVENT_FIELDS)
