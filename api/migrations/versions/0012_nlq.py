"""nlq: view dữ liệu cho AI hỏi đáp, hai role đăng nhập chỉ đọc (nlq_ops, nlq_finance) và nhật ký câu hỏi

Revision ID: 0012

View chỉ chứa cột đã lọc: không SĐT, địa chỉ, MST, mã tra cứu; tên người nhận đã che. Role không có quyền trên bảng gốc,
chỉ SELECT trên view (view chạy bằng quyền chủ sở hữu). Số tiền ở view là đơn vị chính (USD chứ không phải cent).
"""

from alembic import op

from app.config import get_settings

revision = "0012"
down_revision = "0011"

ROLES = ("nlq_ops", "nlq_finance")
OPS_VIEWS = ("v_shipments", "v_trucking", "v_last_mile", "v_container_freetime")
FINANCE_VIEWS = (*OPS_VIEWS, "v_charges")

# Thời điểm hiệu lực của một mốc sau khi bỏ event bị VOID và áp RETIME (bản ghi sau thắng), cùng quy tắc `app.events`.
EFFECTIVE_AT = """
    coalesce((SELECT r.occurred_at FROM {events} r
              WHERE r.kind = 'RETIME' AND r.adjusts_event_id = e.id
                AND NOT EXISTS (SELECT 1 FROM {events} v WHERE v.kind = 'VOID' AND v.adjusts_event_id = r.id)
              ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1), e.occurred_at)"""

FUNCTIONS = """
CREATE FUNCTION nlq.mask_name(name text) RETURNS text LANGUAGE sql IMMUTABLE
SET search_path = pg_catalog AS $$
    SELECT string_agg(left(w.word, 1) || '***', ' ' ORDER BY w.n)
    FROM regexp_split_to_table(btrim(name, E' \\t\\r\\n'), '\\s+') WITH ORDINALITY AS w(word, n)
$$;
"""

VIEWS = f"""
CREATE VIEW nlq.v_shipments AS
SELECT s.code AS shipment_code, s.status, s.load_type, s.delivery_mode,
       c.name AS customer_name, ca.name AS carrier_name,
       pol.code AS pol, pol.name AS pol_name, pod.code AS pod, pod.name AS pod_name,
       s.etd, s.eta, u.full_name AS staff_name,
       (SELECT count(*) FROM containers k WHERE k.shipment_id = s.id)::integer AS container_count,
       s.created_at,
       CASE WHEN s.status = 'COMPLETED' THEN (
           SELECT {EFFECTIVE_AT.format(events="shipment_events")}
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
       (SELECT {EFFECTIVE_AT.format(events="trucking_order_events")}
        FROM trucking_order_events e
        WHERE e.order_id = o.id AND e.kind = 'STARTED'
          AND NOT EXISTS (SELECT 1 FROM trucking_order_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = e.id)
        ORDER BY e.recorded_at DESC, e.id DESC LIMIT 1) AS started_at,
       (SELECT {EFFECTIVE_AT.format(events="trucking_order_events")}
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
       (SELECT {EFFECTIVE_AT.format(events="last_mile_events")}
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
"""

# (view, cột, mô tả tiếng Việt). Cột enum liệt kê các giá trị hợp lệ trong mô tả.
COMMENTS = [
    ("v_shipments", "shipment_code", "Mã lô hàng, dạng FF26xxxxx"),
    ("v_shipments", "status", "Trạng thái lô: CREATED (mới tạo), IN_TRANSIT (đang vận chuyển), ARRIVED (đã đến cảng), "
     "CUSTOMS_CLEARING (đang thông quan), CLEARED (đã thông quan), AT_WAREHOUSE (đã về kho), DELIVERING (đang giao), "
     "COMPLETED (hoàn tất), CANCELLED (đã huỷ)"),
    ("v_shipments", "load_type", "Loại hàng: FCL (nguyên container) hoặc LCL (hàng lẻ)"),
    ("v_shipments", "delivery_mode", "Kiểu giao: VIA_WAREHOUSE (qua kho) hoặc CONTAINER_TO_DOOR (container giao tới cửa)"),
    ("v_shipments", "customer_name", "Tên khách hàng"),
    ("v_shipments", "carrier_name", "Tên hãng tàu, có thể trống"),
    ("v_shipments", "pol", "Mã cảng xếp (POL), ví dụ CNSHA"),
    ("v_shipments", "pol_name", "Tên cảng xếp"),
    ("v_shipments", "pod", "Mã cảng dỡ (POD), ví dụ VNSGN"),
    ("v_shipments", "pod_name", "Tên cảng dỡ"),
    ("v_shipments", "etd", "Ngày dự kiến tàu rời cảng xếp"),
    ("v_shipments", "eta", "Ngày dự kiến tàu đến cảng dỡ"),
    ("v_shipments", "staff_name", "Tên nhân viên phụ trách lô"),
    ("v_shipments", "container_count", "Số container của lô"),
    ("v_shipments", "created_at", "Thời điểm tạo lô"),
    ("v_shipments", "completed_at", "Thời điểm hoàn tất lô, trống nếu chưa hoàn tất"),
    ("v_trucking", "shipment_code", "Mã lô hàng"),
    ("v_trucking", "container_no", "Số container"),
    ("v_trucking", "kind", "Loại lệnh xe: PICKUP_FULL (lấy cont đầy) hoặc RETURN_EMPTY (trả vỏ rỗng)"),
    ("v_trucking", "status", "Trạng thái lệnh: PLANNED, ASSIGNED, STARTED (đang chạy), COMPLETED, CANCELLED"),
    ("v_trucking", "trucker_name", "Tên nhà xe"),
    ("v_trucking", "driver_name", "Tên tài xế, trống nếu chưa phân công"),
    ("v_trucking", "planned_at", "Giờ dự kiến chạy"),
    ("v_trucking", "started_at", "Giờ tài xế bắt đầu chạy, trống nếu chưa"),
    ("v_trucking", "completed_at", "Giờ hoàn tất lệnh, trống nếu chưa"),
    ("v_last_mile", "shipment_code", "Mã lô hàng"),
    ("v_last_mile", "recipient_masked", "Tên người nhận đã che, ví dụ N*** V*** A***"),
    ("v_last_mile", "packages", "Số kiện của đơn giao"),
    ("v_last_mile", "weight_kg", "Trọng lượng (kg), có thể trống"),
    ("v_last_mile", "status", "Trạng thái đơn giao: CREATED (chờ phân công), ASSIGNED (chờ giao), PICKED_UP (đang giao), "
     "DELIVERED (đã giao), FAILED (giao thất bại), RETURNED (hoàn về kho), CANCELLED (đã huỷ)"),
    ("v_last_mile", "planned_date", "Ngày dự kiến giao"),
    ("v_last_mile", "delivered_at", "Thời điểm giao xong, trống nếu chưa giao"),
    ("v_last_mile", "driver_name", "Tên tài xế giao, trống nếu chưa phân công"),
    ("v_charges", "shipment_code", "Mã lô hàng"),
    ("v_charges", "customer_name", "Tên khách hàng của lô"),
    ("v_charges", "carrier_name", "Tên hãng tàu của lô, có thể trống"),
    ("v_charges", "direction", "Chiều khoản: REVENUE (thu khách) hoặc COST (chi)"),
    ("v_charges", "category", "Loại khoản: OCEAN_FREIGHT, THC, LOCAL_CHARGE, TRUCKING, DEM, DET, DND_COMBINED, CUSTOMS, "
     "LAST_MILE, OTHER"),
    ("v_charges", "amount", "Số tiền theo đơn vị chính của loại tiền (USD là đô la, không phải cent; VND là đồng)"),
    ("v_charges", "currency", "Loại tiền: VND hoặc USD"),
    ("v_charges", "amount_vnd", "Số tiền quy đổi ra đồng (VND) theo tỷ giá lúc ghi"),
    ("v_charges", "charge_date", "Ngày ghi khoản (giờ Việt Nam), dùng để tính theo tháng"),
]

LOG_TABLE = """
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
"""


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create_roles() -> None:
    settings = get_settings()
    passwords = {"nlq_ops": settings.nlq_ops_password, "nlq_finance": settings.nlq_finance_password}
    for role, password in passwords.items():
        if not password:
            raise RuntimeError(f"Đặt {role.upper()}_PASSWORD trong .env trước khi chạy migration 0012")
        # Role dùng chung cả cluster (DB chính và DB test) nên tạo nếu chưa có, còn lại chỉ cập nhật mật khẩu.
        op.execute(f"""
DO $do$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
        CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {_literal(password)};
    ELSE
        ALTER ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {_literal(password)};
    END IF;
END $do$""")
        op.execute(f"ALTER ROLE {role} SET default_transaction_read_only = on")
        op.execute(f"ALTER ROLE {role} SET search_path = nlq, public, pg_catalog")
        op.execute(f"DO $do$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {role}', current_database()); END $do$")
        op.execute(f"GRANT USAGE ON SCHEMA nlq, public TO {role}")  # public: để gọi nlq_today(); vẫn không có quyền bảng
        op.execute(f"GRANT EXECUTE ON FUNCTION nlq_today(), nlq.mask_name(text), container_freetime(date) TO {role}")
    for role, views in (("nlq_ops", OPS_VIEWS), ("nlq_finance", FINANCE_VIEWS)):
        for view in views:
            op.execute(f"GRANT SELECT ON nlq.{view} TO {role}")


def upgrade() -> None:
    op.execute(FUNCTIONS)
    op.execute("REVOKE ALL ON FUNCTION nlq.mask_name(text) FROM PUBLIC")
    op.execute(VIEWS)
    for view, column, text in COMMENTS:
        op.execute(f"COMMENT ON COLUMN nlq.{view}.{column} IS {_literal(text)}")
    op.execute(LOG_TABLE)
    _create_roles()


def downgrade() -> None:
    for role, views in (("nlq_ops", OPS_VIEWS), ("nlq_finance", FINANCE_VIEWS)):
        for view in views:
            op.execute(f"REVOKE SELECT ON nlq.{view} FROM {role}")
    op.execute("DROP TABLE nl_query_logs")
    op.execute("DROP VIEW nlq.v_charges, nlq.v_last_mile, nlq.v_trucking, nlq.v_shipments")
    op.execute("DROP FUNCTION nlq.mask_name(text)")
