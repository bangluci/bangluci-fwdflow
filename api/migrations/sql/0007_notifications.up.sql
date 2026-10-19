-- Sinh tự động từ migrations/versions/0007_notifications.py (upgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

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
