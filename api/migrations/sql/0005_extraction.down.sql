-- Sinh tự động từ migrations/versions/0005_extraction.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

DROP TABLE discrepancy_acks, extractions;
