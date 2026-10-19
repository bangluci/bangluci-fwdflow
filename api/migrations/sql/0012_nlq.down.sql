-- Sinh tự động từ migrations/versions/0012_nlq.py (downgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

REVOKE SELECT ON nlq.v_shipments FROM nlq_ops;

REVOKE SELECT ON nlq.v_trucking FROM nlq_ops;

REVOKE SELECT ON nlq.v_last_mile FROM nlq_ops;

REVOKE SELECT ON nlq.v_container_freetime FROM nlq_ops;

REVOKE SELECT ON nlq.v_shipments FROM nlq_finance;

REVOKE SELECT ON nlq.v_trucking FROM nlq_finance;

REVOKE SELECT ON nlq.v_last_mile FROM nlq_finance;

REVOKE SELECT ON nlq.v_container_freetime FROM nlq_finance;

REVOKE SELECT ON nlq.v_charges FROM nlq_finance;

DROP TABLE nl_query_logs;

DROP VIEW nlq.v_charges, nlq.v_last_mile, nlq.v_trucking, nlq.v_shipments;

DROP FUNCTION nlq.mask_name(text);
