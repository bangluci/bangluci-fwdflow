-- Sinh tự động từ migrations/versions/0001_core.py (upgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

CREATE EXTENSION IF NOT EXISTS vector;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE EXTENSION IF NOT EXISTS unaccent;

ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

DO $$ BEGIN EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database()); END $$;

CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'P0001';
END $$;

CREATE TABLE users (
    id              bigserial PRIMARY KEY,
    email           text UNIQUE,
    phone           text UNIQUE,
    full_name       text NOT NULL,
    role            text NOT NULL CHECK (role IN
                      ('ADMIN','DOCS','DISPATCH','ACCOUNTANT','CUSTOMER','DRIVER')),
    customer_id     bigint,
    driver_id       bigint,
    password_hash   text NOT NULL,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (email IS NOT NULL OR phone IS NOT NULL),
    CHECK (email = lower(email)),
    CHECK (role <> 'CUSTOMER' OR customer_id IS NOT NULL),
    CHECK (role <> 'DRIVER' OR driver_id IS NOT NULL)
);

CREATE TABLE sessions (
    id                  bigserial PRIMARY KEY,
    user_id             bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash          bytea NOT NULL UNIQUE,
    created_at          timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    absolute_expires_at timestamptz NOT NULL,
    ip                  text,
    user_agent          text
);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE login_attempts (
    id          bigserial PRIMARY KEY,
    identifier  text NOT NULL,
    ip          text NOT NULL,
    succeeded   boolean NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_login_attempts_pair ON login_attempts (identifier, ip, created_at);

CREATE INDEX ix_login_attempts_ip ON login_attempts (ip, created_at);

CREATE TABLE audit_logs (
    id          bigserial PRIMARY KEY,
    actor_id    bigint REFERENCES users(id),
    action      text NOT NULL,
    entity      text NOT NULL,
    entity_id   text,
    before      jsonb,
    after       jsonb,
    ip          text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_audit_logs_entity ON audit_logs (entity, entity_id);

CREATE INDEX ix_audit_logs_actor ON audit_logs (actor_id, created_at);

CREATE INDEX ix_audit_logs_created ON audit_logs (created_at);

CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
