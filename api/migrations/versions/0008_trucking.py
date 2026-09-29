"""trucking: lệnh điều xe container (lấy hàng đầy, trả vỏ rỗng) và event append-only

Revision ID: 0008
"""

from alembic import op

revision = "0008"
down_revision = "0007"

TABLES = """
CREATE TABLE trucking_orders (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id      bigint NOT NULL REFERENCES shipments(id),
    container_id     bigint NOT NULL REFERENCES containers(id),
    kind             text NOT NULL CHECK (kind IN ('PICKUP_FULL', 'RETURN_EMPTY')),
    trucker_id       bigint NOT NULL REFERENCES truckers(id),
    truck_id         bigint REFERENCES trucks(id),
    driver_id        bigint REFERENCES drivers(id),
    pickup_location  text NOT NULL CHECK (btrim(pickup_location) <> ''),
    drop_location    text NOT NULL CHECK (btrim(drop_location) <> ''),
    planned_at       timestamptz NOT NULL,
    status           text NOT NULL DEFAULT 'PLANNED'
        CHECK (status IN ('PLANNED', 'ASSIGNED', 'STARTED', 'COMPLETED', 'CANCELLED')),
    created_by_id    bigint REFERENCES users(id),
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_trucking_orders_assigned
        CHECK (status IN ('PLANNED', 'CANCELLED') OR (truck_id IS NOT NULL AND driver_id IS NOT NULL))
);
CREATE UNIQUE INDEX uq_trucking_orders_active ON trucking_orders (container_id, kind) WHERE status <> 'CANCELLED';
CREATE INDEX ix_trucking_orders_shipment ON trucking_orders (shipment_id);
CREATE INDEX ix_trucking_orders_planned ON trucking_orders (planned_at);
CREATE INDEX ix_trucking_orders_driver ON trucking_orders (driver_id) WHERE status IN ('ASSIGNED', 'STARTED');

CREATE TABLE trucking_order_events (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id          bigint NOT NULL REFERENCES trucking_orders(id),
    kind              text NOT NULL
        CHECK (kind IN ('ASSIGNED', 'STARTED', 'COMPLETED', 'CANCELLED', 'REASSIGNED', 'RETIME', 'VOID')),
    occurred_at       timestamptz NOT NULL,
    recorded_at       timestamptz NOT NULL DEFAULT now(),
    actor_id          bigint REFERENCES users(id),
    adjusts_event_id  bigint REFERENCES trucking_order_events(id),
    reason            text,
    truck_id          bigint REFERENCES trucks(id),
    driver_id         bigint REFERENCES drivers(id),
    photo_sha256      char(64),
    signer_name       text,
    lat               numeric(9, 6),
    lng               numeric(9, 6),
    device_time       timestamptz,
    client_request_id uuid UNIQUE
);
CREATE INDEX ix_trucking_order_events_order ON trucking_order_events (order_id);
CREATE TRIGGER trucking_order_events_append_only BEFORE UPDATE OR DELETE ON trucking_order_events
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
"""


def upgrade() -> None:
    op.execute(TABLES)


def downgrade() -> None:
    op.execute("DROP TRIGGER trucking_order_events_append_only ON trucking_order_events")
    op.execute("DROP TABLE trucking_order_events, trucking_orders")
