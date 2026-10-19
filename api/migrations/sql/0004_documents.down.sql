-- Sinh tự động từ migrations/versions/0004_documents.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

DROP TABLE required_doc_rules, documents;
