-- Sinh tự động từ migrations/versions/0002_catalog.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_customer;
ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_driver;
DROP TABLE IF EXISTS drivers, trucks, truckers, warehouses, ports, carriers, customers;
