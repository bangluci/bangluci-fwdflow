-- Sinh tự động từ migrations/versions/0012_nlq.py (upgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

CREATE FUNCTION nlq.mask_name(name text) RETURNS text LANGUAGE sql IMMUTABLE
SET search_path = pg_catalog AS $$
    SELECT string_agg(left(w.word, 1) || '***', ' ' ORDER BY w.n)
    FROM regexp_split_to_table(btrim(name, E' \t\r\n'), '\s+') WITH ORDINALITY AS w(word, n)
$$;

REVOKE ALL ON FUNCTION nlq.mask_name(text) FROM PUBLIC;

CREATE VIEW nlq.v_shipments AS
SELECT s.code AS shipment_code, s.status, s.load_type, s.delivery_mode,
       c.name AS customer_name, ca.name AS carrier_name,
       pol.code AS pol, pol.name AS pol_name, pod.code AS pod, pod.name AS pod_name,
       s.etd, s.eta, u.full_name AS staff_name,
       (SELECT count(*) FROM containers k WHERE k.shipment_id = s.id)::integer AS container_count,
       s.created_at,
       CASE WHEN s.status = 'COMPLETED' THEN (
           SELECT 
    coalesce((SELECT r.occurred_at FROM shipment_events r
              WHERE r.kind = 'RETIME' AND r.adjusts_event_id = e.id
                AND NOT EXISTS (SELECT 1 FROM shipment_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = r.id)
              ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1), e.occurred_at)
           FROM shipment_events e
           WHERE e.shipment_id = s.id AND e.kind = 'TRANSITION' AND e.to_status = 'COMPLETED'
             AND NOT EXISTS (SELECT 1 FROM shipment_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = e.id)
           ORDER BY e.recorded_at DESC, e.id DESC LIMIT 1) END AS completed_at
FROM shipments s
JOIN customers c ON c.id = s.customer_id
JOIN users u ON u.id = s.staff_id
LEFT JOIN carriers ca ON ca.id = s.carrier_id
LEFT JOIN ports pol ON pol.id = s.pol_port_id
LEFT JOIN ports pod ON pod.id = s.pod_port_id;

CREATE VIEW nlq.v_trucking AS
SELECT s.code AS shipment_code, k.container_no, o.kind, o.status,
       t.name AS trucker_name, d.full_name AS driver_name, o.planned_at,
       (SELECT 
    coalesce((SELECT r.occurred_at FROM trucking_order_events r
              WHERE r.kind = 'RETIME' AND r.adjusts_event_id = e.id
                AND NOT EXISTS (SELECT 1 FROM trucking_order_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = r.id)
              ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1), e.occurred_at)
        FROM trucking_order_events e
        WHERE e.order_id = o.id AND e.kind = 'STARTED'
          AND NOT EXISTS (SELECT 1 FROM trucking_order_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = e.id)
        ORDER BY e.recorded_at DESC, e.id DESC LIMIT 1) AS started_at,
       (SELECT 
    coalesce((SELECT r.occurred_at FROM trucking_order_events r
              WHERE r.kind = 'RETIME' AND r.adjusts_event_id = e.id
                AND NOT EXISTS (SELECT 1 FROM trucking_order_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = r.id)
              ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1), e.occurred_at)
        FROM trucking_order_events e
        WHERE e.order_id = o.id AND e.kind = 'COMPLETED'
          AND NOT EXISTS (SELECT 1 FROM trucking_order_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = e.id)
        ORDER BY e.recorded_at DESC, e.id DESC LIMIT 1) AS completed_at
FROM trucking_orders o
JOIN shipments s ON s.id = o.shipment_id
JOIN containers k ON k.id = o.container_id
JOIN truckers t ON t.id = o.trucker_id
LEFT JOIN drivers d ON d.id = o.driver_id;

CREATE VIEW nlq.v_last_mile AS
SELECT s.code AS shipment_code, nlq.mask_name(o.recipient_name) AS recipient_masked, o.packages, o.weight_kg,
       o.status, o.planned_date,
       (SELECT 
    coalesce((SELECT r.occurred_at FROM last_mile_events r
              WHERE r.kind = 'RETIME' AND r.adjusts_event_id = e.id
                AND NOT EXISTS (SELECT 1 FROM last_mile_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = r.id)
              ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1), e.occurred_at)
        FROM last_mile_events e
        WHERE e.order_id = o.id AND e.kind = 'DELIVERED'
          AND NOT EXISTS (SELECT 1 FROM last_mile_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = e.id)
        ORDER BY e.recorded_at DESC, e.id DESC LIMIT 1) AS delivered_at,
       d.full_name AS driver_name
FROM last_mile_orders o
JOIN shipments s ON s.id = o.shipment_id
LEFT JOIN drivers d ON d.id = o.driver_id;

CREATE VIEW nlq.v_charges AS
SELECT s.code AS shipment_code, c.name AS customer_name, ca.name AS carrier_name,
       ch.direction, ch.category,
       (CASE ch.currency WHEN 'VND' THEN ch.amount::numeric ELSE ch.amount::numeric / 100 END)::numeric(18, 2) AS amount,
       ch.currency, ch.amount_vnd, ch.charge_date
FROM charges ch
JOIN shipments s ON s.id = ch.shipment_id
JOIN customers c ON c.id = s.customer_id
LEFT JOIN carriers ca ON ca.id = s.carrier_id;

COMMENT ON COLUMN nlq.v_shipments.shipment_code IS 'Mã lô hàng, dạng FF26xxxxx';

COMMENT ON COLUMN nlq.v_shipments.status IS 'Trạng thái lô: CREATED (mới tạo), IN_TRANSIT (đang vận chuyển), ARRIVED (đã đến cảng), CUSTOMS_CLEARING (đang thông quan), CLEARED (đã thông quan), AT_WAREHOUSE (đã về kho), DELIVERING (đang giao), COMPLETED (hoàn tất), CANCELLED (đã huỷ)';

COMMENT ON COLUMN nlq.v_shipments.load_type IS 'Loại hàng: FCL (nguyên container) hoặc LCL (hàng lẻ)';

COMMENT ON COLUMN nlq.v_shipments.delivery_mode IS 'Kiểu giao: VIA_WAREHOUSE (qua kho) hoặc CONTAINER_TO_DOOR (container giao tới cửa)';

COMMENT ON COLUMN nlq.v_shipments.customer_name IS 'Tên khách hàng';

COMMENT ON COLUMN nlq.v_shipments.carrier_name IS 'Tên hãng tàu, có thể trống';

COMMENT ON COLUMN nlq.v_shipments.pol IS 'Mã cảng xếp (POL), ví dụ CNSHA';

COMMENT ON COLUMN nlq.v_shipments.pol_name IS 'Tên cảng xếp';

COMMENT ON COLUMN nlq.v_shipments.pod IS 'Mã cảng dỡ (POD), ví dụ VNSGN';

COMMENT ON COLUMN nlq.v_shipments.pod_name IS 'Tên cảng dỡ';

COMMENT ON COLUMN nlq.v_shipments.etd IS 'Ngày dự kiến tàu rời cảng xếp';

COMMENT ON COLUMN nlq.v_shipments.eta IS 'Ngày dự kiến tàu đến cảng dỡ';

COMMENT ON COLUMN nlq.v_shipments.staff_name IS 'Tên nhân viên phụ trách lô';

COMMENT ON COLUMN nlq.v_shipments.container_count IS 'Số container của lô';

COMMENT ON COLUMN nlq.v_shipments.created_at IS 'Thời điểm tạo lô';

COMMENT ON COLUMN nlq.v_shipments.completed_at IS 'Thời điểm hoàn tất lô, trống nếu chưa hoàn tất';

COMMENT ON COLUMN nlq.v_trucking.shipment_code IS 'Mã lô hàng';

COMMENT ON COLUMN nlq.v_trucking.container_no IS 'Số container';

COMMENT ON COLUMN nlq.v_trucking.kind IS 'Loại lệnh xe: PICKUP_FULL (lấy cont đầy) hoặc RETURN_EMPTY (trả vỏ rỗng)';

COMMENT ON COLUMN nlq.v_trucking.status IS 'Trạng thái lệnh: PLANNED, ASSIGNED, STARTED (đang chạy), COMPLETED, CANCELLED';

COMMENT ON COLUMN nlq.v_trucking.trucker_name IS 'Tên nhà xe';

COMMENT ON COLUMN nlq.v_trucking.driver_name IS 'Tên tài xế, trống nếu chưa phân công';

COMMENT ON COLUMN nlq.v_trucking.planned_at IS 'Giờ dự kiến chạy';

COMMENT ON COLUMN nlq.v_trucking.started_at IS 'Giờ tài xế bắt đầu chạy, trống nếu chưa';

COMMENT ON COLUMN nlq.v_trucking.completed_at IS 'Giờ hoàn tất lệnh, trống nếu chưa';

COMMENT ON COLUMN nlq.v_last_mile.shipment_code IS 'Mã lô hàng';

COMMENT ON COLUMN nlq.v_last_mile.recipient_masked IS 'Tên người nhận đã che, ví dụ N*** V*** A***';

COMMENT ON COLUMN nlq.v_last_mile.packages IS 'Số kiện của đơn giao';

COMMENT ON COLUMN nlq.v_last_mile.weight_kg IS 'Trọng lượng (kg), có thể trống';

COMMENT ON COLUMN nlq.v_last_mile.status IS 'Trạng thái đơn giao: CREATED (chờ phân công), ASSIGNED (chờ giao), PICKED_UP (đang giao), DELIVERED (đã giao), FAILED (giao thất bại), RETURNED (hoàn về kho), CANCELLED (đã huỷ)';

COMMENT ON COLUMN nlq.v_last_mile.planned_date IS 'Ngày dự kiến giao';

COMMENT ON COLUMN nlq.v_last_mile.delivered_at IS 'Thời điểm giao xong, trống nếu chưa giao';

COMMENT ON COLUMN nlq.v_last_mile.driver_name IS 'Tên tài xế giao, trống nếu chưa phân công';

COMMENT ON COLUMN nlq.v_charges.shipment_code IS 'Mã lô hàng';

COMMENT ON COLUMN nlq.v_charges.customer_name IS 'Tên khách hàng của lô';

COMMENT ON COLUMN nlq.v_charges.carrier_name IS 'Tên hãng tàu của lô, có thể trống';

COMMENT ON COLUMN nlq.v_charges.direction IS 'Chiều khoản: REVENUE (thu khách) hoặc COST (chi)';

COMMENT ON COLUMN nlq.v_charges.category IS 'Loại khoản: OCEAN_FREIGHT, THC, LOCAL_CHARGE, TRUCKING, DEM, DET, DND_COMBINED, CUSTOMS, LAST_MILE, OTHER';

COMMENT ON COLUMN nlq.v_charges.amount IS 'Số tiền theo đơn vị chính của loại tiền (USD là đô la, không phải cent; VND là đồng)';

COMMENT ON COLUMN nlq.v_charges.currency IS 'Loại tiền: VND hoặc USD';

COMMENT ON COLUMN nlq.v_charges.amount_vnd IS 'Số tiền quy đổi ra đồng (VND) theo tỷ giá lúc ghi';

COMMENT ON COLUMN nlq.v_charges.charge_date IS 'Ngày ghi khoản (giờ Việt Nam), dùng để tính theo tháng';

CREATE TABLE nl_query_logs (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           bigint NOT NULL REFERENCES users(id),
    nlq_role          text NOT NULL CHECK (nlq_role IN ('nlq_ops', 'nlq_finance')),
    question          text NOT NULL,
    sql_generated     text,
    sql_final         text,
    validation_result text NOT NULL CHECK (validation_result IN ('OK', 'REJECTED', 'NO_PERMISSION')),
    error_code        text,
    repaired          boolean NOT NULL DEFAULT false,
    row_count         integer,
    truncated         boolean NOT NULL DEFAULT false,
    answer_checked    boolean,
    user_rating       boolean,
    usage             jsonb,
    latency_ms        integer NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_nl_query_logs_user_created ON nl_query_logs (user_id, created_at);

DO $do$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nlq_ops') THEN
        CREATE ROLE nlq_ops LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '<NLQ_OPS_PASSWORD>';
    ELSE
        ALTER ROLE nlq_ops LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '<NLQ_OPS_PASSWORD>';
    END IF;
END $do$;

ALTER ROLE nlq_ops SET default_transaction_read_only = on;

ALTER ROLE nlq_ops SET search_path = nlq, public, pg_catalog;

DO $do$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO nlq_ops', current_database()); END $do$;

GRANT USAGE ON SCHEMA nlq, public TO nlq_ops;

GRANT EXECUTE ON FUNCTION nlq_today(), nlq.mask_name(text), container_freetime(date) TO nlq_ops;

DO $do$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nlq_finance') THEN
        CREATE ROLE nlq_finance LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '<NLQ_FINANCE_PASSWORD>';
    ELSE
        ALTER ROLE nlq_finance LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '<NLQ_FINANCE_PASSWORD>';
    END IF;
END $do$;

ALTER ROLE nlq_finance SET default_transaction_read_only = on;

ALTER ROLE nlq_finance SET search_path = nlq, public, pg_catalog;

DO $do$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO nlq_finance', current_database()); END $do$;

GRANT USAGE ON SCHEMA nlq, public TO nlq_finance;

GRANT EXECUTE ON FUNCTION nlq_today(), nlq.mask_name(text), container_freetime(date) TO nlq_finance;

GRANT SELECT ON nlq.v_shipments TO nlq_ops;

GRANT SELECT ON nlq.v_trucking TO nlq_ops;

GRANT SELECT ON nlq.v_last_mile TO nlq_ops;

GRANT SELECT ON nlq.v_container_freetime TO nlq_ops;

GRANT SELECT ON nlq.v_shipments TO nlq_finance;

GRANT SELECT ON nlq.v_trucking TO nlq_finance;

GRANT SELECT ON nlq.v_last_mile TO nlq_finance;

GRANT SELECT ON nlq.v_container_freetime TO nlq_finance;

GRANT SELECT ON nlq.v_charges TO nlq_finance;
