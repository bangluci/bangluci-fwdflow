-- Sinh tự động từ migrations/versions/0011_hs.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

DROP TABLE hs_suggestion_logs;

DROP TABLE hs_codes;

DROP TEXT SEARCH CONFIGURATION vn_simple;
