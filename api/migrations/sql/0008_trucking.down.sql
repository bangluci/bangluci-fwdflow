-- Sinh tự động từ migrations/versions/0008_trucking.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

DROP TRIGGER trucking_order_events_append_only ON trucking_order_events;

DROP TABLE trucking_order_events, trucking_orders;
