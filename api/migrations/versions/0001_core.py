"""core: extensions, append-only trigger, users, sessions, login_attempts, audit_logs

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # Hàm tự viết không cấp EXECUTE cho PUBLIC; bảng tạm chỉ cho role app (không cho role nlq_*).
    op.execute("ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database()); END $$"
    )

    op.execute(
        """
        CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'P0001';
        END $$
        """
    )

    op.execute(
        """
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
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sessions (
            id                  bigserial PRIMARY KEY,
            user_id             bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash          bytea NOT NULL UNIQUE,
            created_at          timestamptz NOT NULL DEFAULT now(),
            last_seen_at        timestamptz NOT NULL DEFAULT now(),
            absolute_expires_at timestamptz NOT NULL,
            ip                  text,
            user_agent          text
        )
        """
    )
    op.execute("CREATE INDEX ix_sessions_user_id ON sessions (user_id)")
    op.execute(
        """
        CREATE TABLE login_attempts (
            id          bigserial PRIMARY KEY,
            identifier  text NOT NULL,
            ip          text NOT NULL,
            succeeded   boolean NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_login_attempts_pair ON login_attempts (identifier, ip, created_at)")
    op.execute("CREATE INDEX ix_login_attempts_ip ON login_attempts (ip, created_at)")
    op.execute(
        """
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
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_logs_entity ON audit_logs (entity, entity_id)")
    op.execute("CREATE INDEX ix_audit_logs_actor ON audit_logs (actor_id, created_at)")
    op.execute("CREATE INDEX ix_audit_logs_created ON audit_logs (created_at)")
    op.execute(
        "CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs, login_attempts, sessions, users CASCADE")
    op.execute("DROP FUNCTION IF EXISTS forbid_mutation()")
