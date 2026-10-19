-- Sinh tự động từ migrations/versions/0006_freetime.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

DROP VIEW IF EXISTS nlq.v_container_freetime;

DROP FUNCTION IF EXISTS container_freetime(date);

DROP VIEW IF EXISTS effective_container_milestones;

DROP FUNCTION IF EXISTS freetime_level_rank(text);

DROP FUNCTION IF EXISTS nlq_today();

DROP SCHEMA IF EXISTS nlq;

DROP TABLE shipment_free_time_overrides, free_time_tiers, free_time_rules;
