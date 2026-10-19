-- Sinh tự động từ migrations/versions/0009_last_mile.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

ALTER TABLE shipment_events DROP COLUMN photo_sha256;

DROP TRIGGER last_mile_events_append_only ON last_mile_events;

DROP TABLE last_mile_events, last_mile_orders;
