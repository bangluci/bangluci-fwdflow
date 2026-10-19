-- Sinh tự động từ migrations/versions/0003_shipments.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

DROP TABLE container_events, shipment_events, containers, customs_declarations, shipment_items, shipments;
DROP SEQUENCE shipment_code_seq;
