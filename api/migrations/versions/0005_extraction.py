"""extraction: AI extraction queue and results, discrepancy acknowledgements

Revision ID: 0005
"""

from alembic import op

revision = "0005"
down_revision = "0004"

STATUSES = ("PENDING", "PROCESSING", "REVIEW", "APPROVED", "REJECTED", "FAILED", "CANCELLED")


def upgrade() -> None:
    statuses = ", ".join(f"'{s}'" for s in STATUSES)
    op.execute(
        f"""
        CREATE TABLE extractions (
            id                  bigserial PRIMARY KEY,
            document_id         bigint NOT NULL UNIQUE REFERENCES documents(id),
            shipment_id         bigint NOT NULL REFERENCES shipments(id),
            doc_type            text NOT NULL CHECK (doc_type IN ('MBL', 'HBL', 'INVOICE', 'PACKING_LIST')),
            status              text NOT NULL DEFAULT 'PENDING' CHECK (status IN ({statuses})),
            attempts            integer NOT NULL DEFAULT 0,
            next_attempt_at     timestamptz NOT NULL DEFAULT now(),
            locked_at           timestamptz,
            processed_at        timestamptz,
            config              jsonb,
            usage               jsonb NOT NULL DEFAULT '{{}}',
            stop_reason         text,
            latency_ms          integer,
            result              jsonb,
            raw_output          text,
            field_issues        jsonb NOT NULL DEFAULT '[]',
            detected_doc_type   text,
            suspicious_content  boolean NOT NULL DEFAULT false,
            suspicious_note     text,
            error_code          text,
            error_message       text,
            approved_result     jsonb,
            edited_fields       text[] NOT NULL DEFAULT '{{}}',
            manual_check_done   boolean NOT NULL DEFAULT false,
            reviewed_by         bigint REFERENCES users(id),
            reviewed_at         timestamptz,
            reject_reason       text,
            version             integer NOT NULL DEFAULT 1,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_extractions_queue ON extractions (status, next_attempt_at);
        CREATE INDEX ix_extractions_shipment ON extractions (shipment_id);

        CREATE TABLE discrepancy_acks (
            id                bigserial PRIMARY KEY,
            shipment_id       bigint NOT NULL REFERENCES shipments(id),
            discrepancy_key   text NOT NULL,
            reason            text NOT NULL CHECK (length(btrim(reason)) >= 3),
            acked_by          bigint NOT NULL REFERENCES users(id),
            acked_at          timestamptz NOT NULL DEFAULT now(),
            UNIQUE (shipment_id, discrepancy_key)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE discrepancy_acks, extractions")
