"""shipments: shipments, items, customs declarations, containers and two append-only event tables

Revision ID: 0003
"""

from alembic import op

revision = "0003"
down_revision = "0002"

STATUSES = ("CREATED", "IN_TRANSIT", "ARRIVED", "CUSTOMS_CLEARING", "CLEARED", "AT_WAREHOUSE", "DELIVERING",
            "COMPLETED", "CANCELLED")
CONTAINER_TYPES = ("20GP", "40GP", "40HC", "45HC", "20RF", "40RF", "40RH")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute("CREATE SEQUENCE shipment_code_seq")
    op.execute(
        f"""
        CREATE TABLE shipments (
            id                bigserial PRIMARY KEY,
            code              text NOT NULL UNIQUE DEFAULT 'FF' || to_char(now() AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YY')
                                  || lpad(nextval('shipment_code_seq')::text, 5, '0'),
            load_type         text NOT NULL CHECK (load_type IN ('FCL', 'LCL')),
            delivery_mode     text NOT NULL CHECK (delivery_mode IN ('VIA_WAREHOUSE', 'CONTAINER_TO_DOOR')),
            customer_id       bigint NOT NULL REFERENCES customers(id),
            staff_id          bigint NOT NULL REFERENCES users(id),
            carrier_id        bigint REFERENCES carriers(id),
            pol_port_id       bigint REFERENCES ports(id),
            pod_port_id       bigint REFERENCES ports(id),
            dest_warehouse_id bigint REFERENCES warehouses(id),
            mbl_no            text,
            hbl_no            text,
            vessel            text,
            voyage            text,
            etd               date,
            eta               date,
            claims_fta        boolean NOT NULL DEFAULT false,
            do_no             text,
            do_valid_until    date,
            total_packages    integer CHECK (total_packages >= 0),
            version           integer NOT NULL DEFAULT 1,
            status            text NOT NULL DEFAULT 'CREATED' CHECK (status IN ({_in(STATUSES)})),
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_shipments_lcl_via_warehouse CHECK (load_type = 'FCL' OR delivery_mode = 'VIA_WAREHOUSE')
        );
        CREATE INDEX ix_shipments_customer ON shipments (customer_id);
        CREATE INDEX ix_shipments_status ON shipments (status);
        CREATE INDEX ix_shipments_eta ON shipments (eta);

        CREATE TABLE shipment_items (
            id              bigserial PRIMARY KEY,
            shipment_id     bigint NOT NULL REFERENCES shipments(id),
            line_no         integer NOT NULL,
            description     text NOT NULL,
            quantity        numeric(18, 3) NOT NULL CHECK (quantity > 0),
            unit            text,
            packages        integer CHECK (packages >= 0),
            gross_weight_kg numeric(14, 3) CHECK (gross_weight_kg >= 0),
            value_amount    bigint CHECK (value_amount >= 0),
            value_currency  char(3),
            hs_code         char(8) CHECK (hs_code ~ '^[0-9]{{8}}$'),
            hs_source       text CHECK (hs_source IN ('manual', 'ai_accepted')),
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (shipment_id, line_no),
            CONSTRAINT ck_shipment_items_hs_pair CHECK ((hs_code IS NULL) = (hs_source IS NULL))
        );

        CREATE TABLE customs_declarations (
            id             bigserial PRIMARY KEY,
            shipment_id    bigint NOT NULL REFERENCES shipments(id),
            declaration_no char(12) NOT NULL UNIQUE CHECK (declaration_no ~ '^[0-9]{{12}}$'),
            type_code      text NOT NULL CHECK (type_code ~ '^[A-Z][0-9]{{2}}$'),
            registered_at  timestamptz NOT NULL,
            lane           text CHECK (lane IN ('GREEN', 'YELLOW', 'RED')),
            cleared_at     timestamptz,
            created_at     timestamptz NOT NULL DEFAULT now(),
            updated_at     timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_customs_declarations_cleared_after CHECK (cleared_at IS NULL OR cleared_at >= registered_at)
        );

        CREATE TABLE containers (
            id              bigserial PRIMARY KEY,
            shipment_id     bigint NOT NULL REFERENCES shipments(id),
            container_no    char(11) NOT NULL CHECK (container_no ~ '^[A-Z]{{4}}[0-9]{{7}}$'),
            container_type  text NOT NULL CHECK (container_type IN ({_in(CONTAINER_TYPES)})),
            seal_no         text,
            gross_weight_kg numeric(14, 3) CHECK (gross_weight_kg >= 0),
            status          text,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (shipment_id, container_no)
        );
        CREATE INDEX ix_containers_container_no ON containers (container_no);

        CREATE TABLE shipment_events (
            id               bigserial PRIMARY KEY,
            shipment_id      bigint NOT NULL REFERENCES shipments(id),
            kind             text NOT NULL CHECK (kind IN ('TRANSITION', 'RETIME', 'VOID')),
            from_status      text,
            to_status        text,
            occurred_at      timestamptz NOT NULL,
            recorded_at      timestamptz NOT NULL DEFAULT now(),
            actor_id         bigint REFERENCES users(id),
            adjusts_event_id bigint REFERENCES shipment_events(id),
            reason           text
        );
        CREATE INDEX ix_shipment_events_shipment ON shipment_events (shipment_id);

        CREATE TABLE container_events (
            id               bigserial PRIMARY KEY,
            container_id     bigint NOT NULL REFERENCES containers(id),
            kind             text NOT NULL
                CHECK (kind IN ('DISCHARGED', 'GATE_OUT_FULL', 'EMPTY_RETURNED', 'RETIME', 'VOID')),
            occurred_at      timestamptz NOT NULL,
            recorded_at      timestamptz NOT NULL DEFAULT now(),
            actor_id         bigint REFERENCES users(id),
            adjusts_event_id bigint REFERENCES container_events(id),
            reason           text
        );
        CREATE INDEX ix_container_events_container ON container_events (container_id);

        CREATE TRIGGER shipment_events_append_only BEFORE UPDATE OR DELETE ON shipment_events
            FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
        CREATE TRIGGER container_events_append_only BEFORE UPDATE OR DELETE ON container_events
            FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE container_events, shipment_events, containers, customs_declarations, shipment_items, shipments;
        DROP SEQUENCE shipment_code_seq;
        """
    )
