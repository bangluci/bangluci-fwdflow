"""documents: uploaded files metadata and required document rules

Revision ID: 0004
"""

from alembic import op

revision = "0004"
down_revision = "0003"

DOC_TYPES = ("MBL", "HBL", "INVOICE", "PACKING_LIST", "CUSTOMS_DECLARATION", "DO", "ARRIVAL_NOTICE",
             "ORIGIN_PROOF", "SPECIALIZED_INSPECTION", "OTHER")
# (load_type, claims_fta, doc_type, required_from_status): 8 dòng FCL + 7 dòng LCL (LCL không cần MBL)
COMMON_RULES = [
    (None, "HBL", "IN_TRANSIT"), (None, "INVOICE", "IN_TRANSIT"), (None, "PACKING_LIST", "IN_TRANSIT"),
    (None, "ARRIVAL_NOTICE", "ARRIVED"), (True, "ORIGIN_PROOF", "CUSTOMS_CLEARING"),
    (None, "CUSTOMS_DECLARATION", "CLEARED"), (None, "DO", "CLEARED"),
]


def _rule_rows() -> str:
    rows = [("FCL", None, "MBL", "IN_TRANSIT")]
    for load_type in ("FCL", "LCL"):
        rows += [(load_type, fta, doc, status) for fta, doc, status in COMMON_RULES]
    return ", ".join(
        f"('{lt}', {'NULL' if fta is None else str(fta).lower()}, '{doc}', '{status}')" for lt, fta, doc, status in rows
    )


def upgrade() -> None:
    doc_types = ", ".join(f"'{t}'" for t in DOC_TYPES)
    op.execute(
        f"""
        CREATE TABLE documents (
            id                  bigserial PRIMARY KEY,
            shipment_id         bigint NOT NULL REFERENCES shipments(id),
            doc_type            text NOT NULL CHECK (doc_type IN ({doc_types})),
            file_sha256         char(64) NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
            mime                text NOT NULL CHECK (mime IN ('application/pdf', 'image/jpeg')),
            size_bytes          bigint NOT NULL CHECK (size_bytes > 0),
            pages               integer NOT NULL CHECK (pages >= 1),
            original_name       text,
            superseded_by_id    bigint REFERENCES documents(id),
            visible_to_customer boolean NOT NULL,
            uploaded_by         bigint NOT NULL REFERENCES users(id),
            uploaded_at         timestamptz NOT NULL DEFAULT now(),
            UNIQUE (shipment_id, file_sha256)
        );
        CREATE INDEX ix_documents_active_type ON documents (shipment_id, doc_type) WHERE superseded_by_id IS NULL;

        CREATE TABLE required_doc_rules (
            id                   bigserial PRIMARY KEY,
            load_type            text NOT NULL CHECK (load_type IN ('FCL', 'LCL')),
            claims_fta           boolean,
            doc_type             text NOT NULL CHECK (doc_type IN ({doc_types})),
            required_from_status text NOT NULL,
            UNIQUE NULLS NOT DISTINCT (load_type, claims_fta, doc_type)
        );
        INSERT INTO required_doc_rules (load_type, claims_fta, doc_type, required_from_status)
        VALUES {_rule_rows()};
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE required_doc_rules, documents")
