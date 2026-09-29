import pytest

import app.shipments.audit_fields  # noqa: F401 - đăng ký AUDIT_FIELDS
from app.audit.service import AUDIT_FIELDS, PII_FIELDS, SECRET_FIELDS
from app.shipments.models import Container, ContainerEvent, CustomsDeclaration, Shipment, ShipmentEvent, ShipmentItem

MODELS = {"shipment": Shipment, "shipment_item": ShipmentItem, "customs_declaration": CustomsDeclaration,
          "container": Container, "shipment_event": ShipmentEvent, "container_event": ContainerEvent}


@pytest.mark.parametrize("entity", sorted(MODELS))
def test_shipment_audit_fields_are_model_columns(entity):
    columns = {c.key for c in MODELS[entity].__table__.columns}
    assert AUDIT_FIELDS[entity] <= columns
    assert not AUDIT_FIELDS[entity] & (PII_FIELDS | SECRET_FIELDS)
