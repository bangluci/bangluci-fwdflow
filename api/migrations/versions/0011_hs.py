"""hs: danh mục mã HS (TT 31/2022) có tìm kiếm full-text + vector, và nhật ký gợi ý AI #2

Revision ID: 0011
"""

from alembic import op

revision = "0011"
down_revision = "0010"

SCHEMA = """
CREATE TEXT SEARCH CONFIGURATION vn_simple (COPY = simple);
ALTER TEXT SEARCH CONFIGURATION vn_simple ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple;

CREATE TABLE hs_codes (
    code           char(8) PRIMARY KEY CHECK (code ~ '^[0-9]{8}$'),
    chapter        smallint NOT NULL CHECK (chapter BETWEEN 1 AND 97),
    description_vi text NOT NULL,
    description_en text,
    nomenclature   text NOT NULL DEFAULT 'TT31/2022',
    embedding      vector(1024),
    tsv_vi         tsvector GENERATED ALWAYS AS (to_tsvector('vn_simple', description_vi)) STORED,
    tsv_en         tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(description_en, ''))) STORED
);
CREATE INDEX ix_hs_codes_tsv_vi ON hs_codes USING gin (tsv_vi);
CREATE INDEX ix_hs_codes_tsv_en ON hs_codes USING gin (tsv_en);
CREATE INDEX ix_hs_codes_embedding_hnsw ON hs_codes USING hnsw (embedding vector_cosine_ops);

CREATE TABLE hs_suggestion_logs (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id          bigint NOT NULL REFERENCES users(id),
    shipment_item_id bigint REFERENCES shipment_items(id) ON DELETE SET NULL,
    description      text NOT NULL,
    search_degraded  boolean NOT NULL,
    top1_cosine      double precision,
    candidates       jsonb NOT NULL,
    status           text NOT NULL CHECK (status IN ('OK', 'INSUFFICIENT', 'SEARCH_ONLY')),
    top3             jsonb NOT NULL,
    chosen_code      char(8) REFERENCES hs_codes(code),
    chosen_at        timestamptz,
    llm              jsonb,
    latency_ms       integer NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_hs_suggestion_logs_chosen CHECK ((chosen_code IS NULL) = (chosen_at IS NULL))
);
CREATE INDEX ix_hs_suggestion_logs_user_created ON hs_suggestion_logs (user_id, created_at);
"""


def upgrade() -> None:
    op.execute(SCHEMA)


def downgrade() -> None:
    op.execute("DROP TABLE hs_suggestion_logs")
    op.execute("DROP TABLE hs_codes")
    op.execute("DROP TEXT SEARCH CONFIGURATION vn_simple")
