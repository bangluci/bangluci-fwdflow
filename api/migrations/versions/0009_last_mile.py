"""last_mile: đơn giao nội địa, event append-only và ảnh trên event lô (nhận hàng LCL, đóng lô)

Revision ID: 0009
"""

from alembic import op

revision = "0009"
down_revision = "0008"

TABLES = """
CREATE TABLE last_mile_orders (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id      bigint NOT NULL REFERENCES shipments(id),
    tracking_code    char(10) NOT NULL UNIQUE,
    recipient_name   text NOT NULL CHECK (btrim(recipient_name) <> ''),
    recipient_phone  text NOT NULL CHECK (btrim(recipient_phone) <> ''),
    address          text NOT NULL CHECK (btrim(address) <> ''),
    packages         integer NOT NULL CHECK (packages > 0),
    weight_kg        numeric(12, 3) CHECK (weight_kg >= 0),
    driver_id        bigint REFERENCES drivers(id),
    planned_date     date NOT NULL,
    status           text NOT NULL DEFAULT 'CREATED'
        CHECK (status IN ('CREATED', 'ASSIGNED', 'PICKED_UP', 'DELIVERED', 'FAILED', 'RETURNED', 'CANCELLED')),
    created_by       bigint REFERENCES users(id),
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_last_mile_orders_shipment ON last_mile_orders (shipment_id);
CREATE INDEX ix_last_mile_orders_driver_date ON last_mile_orders (driver_id, planned_date);

CREATE TABLE last_mile_events (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id          bigint NOT NULL REFERENCES last_mile_orders(id),
    kind              text NOT NULL CHECK (kind IN ('CREATED', 'ASSIGNED', 'REASSIGNED', 'PICKED_UP', 'DELIVERED',
                                                    'FAILED', 'RETURNED', 'CANCELLED', 'RETIME', 'VOID')),
    occurred_at       timestamptz NOT NULL,
    recorded_at       timestamptz NOT NULL DEFAULT now(),
    actor_id          bigint REFERENCES users(id),
    adjusts_event_id  bigint REFERENCES last_mile_events(id),
    reason            text,
    driver_id         bigint REFERENCES drivers(id),
    photo_sha256      char(64),
    lat               numeric(9, 6),
    lng               numeric(9, 6),
    device_time       timestamptz,
    client_request_id uuid UNIQUE,
    CONSTRAINT ck_last_mile_events_coordinates CHECK ((lat IS NULL) = (lng IS NULL))
);
CREATE INDEX ix_last_mile_events_order ON last_mile_events (order_id);
CREATE TRIGGER last_mile_events_append_only BEFORE UPDATE OR DELETE ON last_mile_events
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

ALTER TABLE shipment_events ADD COLUMN photo_sha256 char(64);
"""


def upgrade() -> None:
    op.execute(TABLES)


def downgrade() -> None:
    op.execute("ALTER TABLE shipment_events DROP COLUMN photo_sha256")
    op.execute("DROP TRIGGER last_mile_events_append_only ON last_mile_events")
    op.execute("DROP TABLE last_mile_events, last_mile_orders")
