"""notifications: nhật ký email nhắc hạn free time (mỗi người nhận một dòng mỗi ngày)

Revision ID: 0007
"""

from alembic import op

revision = "0007"
down_revision = "0006"

TABLES = """
CREATE TABLE notification_logs (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipient        text NOT NULL CHECK (recipient = lower(recipient)),
    day              date NOT NULL,
    status           text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT', 'FAILED')),
    attempts         integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_attempt_at  timestamptz,
    sent_at          timestamptz,
    error            text,
    items            jsonb NOT NULL DEFAULT '[]',
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_notification_logs_recipient_day UNIQUE (recipient, day)
);
CREATE INDEX ix_notification_logs_status_attempt ON notification_logs (status, last_attempt_at);
"""


def upgrade() -> None:
    op.execute(TABLES)


def downgrade() -> None:
    op.execute("DROP TABLE notification_logs")
