-- Sinh tự động từ migrations/versions/0001_core.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

DROP TABLE IF EXISTS audit_logs, login_attempts, sessions, users CASCADE;

DROP FUNCTION IF EXISTS forbid_mutation();
