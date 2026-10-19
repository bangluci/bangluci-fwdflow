-- Sinh tự động từ migrations/versions/0004_documents.py (upgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

CREATE TABLE documents (
    id                  bigserial PRIMARY KEY,
    shipment_id         bigint NOT NULL REFERENCES shipments(id),
    doc_type            text NOT NULL CHECK (doc_type IN ('MBL', 'HBL', 'INVOICE', 'PACKING_LIST', 'CUSTOMS_DECLARATION', 'DO', 'ARRIVAL_NOTICE', 'ORIGIN_PROOF', 'SPECIALIZED_INSPECTION', 'OTHER')),
    file_sha256         char(64) NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
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
    doc_type             text NOT NULL CHECK (doc_type IN ('MBL', 'HBL', 'INVOICE', 'PACKING_LIST', 'CUSTOMS_DECLARATION', 'DO', 'ARRIVAL_NOTICE', 'ORIGIN_PROOF', 'SPECIALIZED_INSPECTION', 'OTHER')),
    required_from_status text NOT NULL,
    UNIQUE NULLS NOT DISTINCT (load_type, claims_fta, doc_type)
);
INSERT INTO required_doc_rules (load_type, claims_fta, doc_type, required_from_status)
VALUES ('FCL', NULL, 'MBL', 'IN_TRANSIT'), ('FCL', NULL, 'HBL', 'IN_TRANSIT'), ('FCL', NULL, 'INVOICE', 'IN_TRANSIT'), ('FCL', NULL, 'PACKING_LIST', 'IN_TRANSIT'), ('FCL', NULL, 'ARRIVAL_NOTICE', 'ARRIVED'), ('FCL', true, 'ORIGIN_PROOF', 'CUSTOMS_CLEARING'), ('FCL', NULL, 'CUSTOMS_DECLARATION', 'CLEARED'), ('FCL', NULL, 'DO', 'CLEARED'), ('LCL', NULL, 'HBL', 'IN_TRANSIT'), ('LCL', NULL, 'INVOICE', 'IN_TRANSIT'), ('LCL', NULL, 'PACKING_LIST', 'IN_TRANSIT'), ('LCL', NULL, 'ARRIVAL_NOTICE', 'ARRIVED'), ('LCL', true, 'ORIGIN_PROOF', 'CUSTOMS_CLEARING'), ('LCL', NULL, 'CUSTOMS_DECLARATION', 'CLEARED'), ('LCL', NULL, 'DO', 'CLEARED');
