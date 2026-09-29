"""freetime: DEM/DET rules, tiers, shipment overrides, and the shared SQL clock function

Revision ID: 0006
"""

from alembic import op

revision = "0006"
down_revision = "0005"

TABLES = """
CREATE TABLE free_time_rules (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    carrier_id     bigint NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
    port_id        bigint NOT NULL REFERENCES ports(id) ON DELETE RESTRICT,
    container_type text NOT NULL CHECK (container_type IN ('20GP', '40GP', '40HC', '45HC', '20RF', '40RF', '40RH')),
    fee_type       text NOT NULL CHECK (fee_type IN ('DEM', 'DET', 'COMBINED')),
    free_days      integer NOT NULL CHECK (free_days BETWEEN 0 AND 365),
    effective_from date NOT NULL,
    created_by     bigint REFERENCES users(id),
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_free_time_rules_key UNIQUE (carrier_id, port_id, container_type, fee_type, effective_from)
);

CREATE TABLE free_time_tiers (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_id     bigint NOT NULL REFERENCES free_time_rules(id) ON DELETE CASCADE,
    from_day    integer NOT NULL CHECK (from_day >= 1),
    to_day      integer,
    rate_amount bigint NOT NULL CHECK (rate_amount >= 0),
    currency    char(3) NOT NULL CHECK (currency IN ('VND', 'USD')),
    CONSTRAINT ck_free_time_tiers_range CHECK (to_day IS NULL OR to_day >= from_day),
    UNIQUE (rule_id, from_day)
);

CREATE TABLE shipment_free_time_overrides (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id bigint NOT NULL REFERENCES shipments(id) ON DELETE RESTRICT,
    fee_type    text NOT NULL CHECK (fee_type IN ('DEM', 'DET', 'COMBINED')),
    free_days   integer NOT NULL CHECK (free_days BETWEEN 0 AND 365),
    source      text NOT NULL CHECK (source IN ('ARRIVAL_NOTICE', 'DO', 'CONTRACT')),
    document_id bigint REFERENCES documents(id),
    created_by  bigint REFERENCES users(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (shipment_id, fee_type)
);
"""

HELPERS = """
CREATE SCHEMA IF NOT EXISTS nlq;

CREATE FUNCTION nlq_today() RETURNS date LANGUAGE sql STABLE
SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT coalesce(nullif(current_setting('app.as_of', true), '')::date,
                    (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
$$;

CREATE FUNCTION freetime_level_rank(level text) RETURNS integer LANGUAGE sql IMMUTABLE
SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT CASE level WHEN 'RED' THEN 5 WHEN 'YELLOW' THEN 4 WHEN 'NO_RULE' THEN 3
                      WHEN 'MISSING_DATA' THEN 2 WHEN 'GREEN' THEN 1 END
$$;

CREATE VIEW effective_container_milestones AS
SELECT DISTINCT ON (e.container_id, e.kind)
       e.container_id,
       e.kind,
       coalesce((SELECT r.occurred_at FROM container_events r
                 WHERE r.kind = 'RETIME' AND r.adjusts_event_id = e.id
                   AND NOT EXISTS (SELECT 1 FROM container_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = r.id)
                 ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1), e.occurred_at) AS occurred_at,
       e.id AS event_id
FROM container_events e
WHERE e.kind IN ('DISCHARGED', 'GATE_OUT_FULL', 'EMPTY_RETURNED')
  AND NOT EXISTS (SELECT 1 FROM container_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = e.id)
ORDER BY e.container_id, e.kind, e.recorded_at DESC, e.id DESC;

REVOKE ALL ON FUNCTION nlq_today() FROM PUBLIC;
REVOKE ALL ON FUNCTION freetime_level_rank(text) FROM PUBLIC;
REVOKE ALL ON effective_container_milestones FROM PUBLIC;
GRANT EXECUTE ON FUNCTION nlq_today() TO CURRENT_USER;
GRANT EXECUTE ON FUNCTION freetime_level_rank(text) TO CURRENT_USER;
GRANT SELECT ON effective_container_milestones TO CURRENT_USER;
"""

# Mỗi container của lô FCL có một dòng cho mỗi đồng hồ (DEM / DET hoặc COMBINED). Tính ra, không lưu.
CLOCK_FUNCTION = """
CREATE FUNCTION container_freetime(as_of date) RETURNS TABLE (
    container_id bigint, container_no text, container_type text, shipment_id bigint, shipment_code text,
    shipment_status text, customer_name text, carrier_name text, pod_code text, eta date,
    fee_type text, rule_source text, status text, level text, container_level text,
    discharged_date date, gate_out_date date, returned_date date, start_date date, end_date date,
    free_days integer, due_date date, days_used integer, days_left integer, days_over integer,
    fee_amount bigint, fee_currency text
) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
WITH milestones AS (
    SELECT container_id,
           (max(occurred_at) FILTER (WHERE kind = 'DISCHARGED') AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS discharged_date,
           (max(occurred_at) FILTER (WHERE kind = 'GATE_OUT_FULL') AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS gate_out_date,
           (max(occurred_at) FILTER (WHERE kind = 'EMPTY_RETURNED') AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS returned_date
    FROM effective_container_milestones GROUP BY container_id
), base AS (
    SELECT c.id AS container_id, c.container_no::text AS container_no, c.container_type,
           s.id AS shipment_id, s.code AS shipment_code, s.status AS shipment_status,
           cu.name AS customer_name, ca.name AS carrier_name, p.code AS pod_code, s.eta,
           s.carrier_id, s.pod_port_id,
           m.discharged_date, m.gate_out_date, m.returned_date,
           coalesce(m.discharged_date, as_of) AS ref_date
    FROM containers c
    JOIN shipments s ON s.id = c.shipment_id AND s.load_type = 'FCL'
    JOIN customers cu ON cu.id = s.customer_id
    LEFT JOIN carriers ca ON ca.id = s.carrier_id
    LEFT JOIN ports p ON p.id = s.pod_port_id
    LEFT JOIN milestones m ON m.container_id = c.id
), rule_set AS (
    SELECT b.container_id, r.id AS rule_id, r.fee_type, r.free_days
    FROM base b
    JOIN free_time_rules r ON r.carrier_id = b.carrier_id AND r.port_id = b.pod_port_id
                          AND r.container_type = b.container_type
    WHERE r.effective_from = (SELECT max(r2.effective_from) FROM free_time_rules r2
                              WHERE r2.carrier_id = r.carrier_id AND r2.port_id = r.port_id
                                AND r2.container_type = r.container_type AND r2.effective_from <= b.ref_date)
), clocks AS (
    SELECT b.container_id, k.fee_type
    FROM base b
    CROSS JOIN LATERAL unnest(CASE
        WHEN EXISTS (SELECT 1 FROM shipment_free_time_overrides o
                     WHERE o.shipment_id = b.shipment_id AND o.fee_type = 'COMBINED') THEN ARRAY['COMBINED']
        WHEN EXISTS (SELECT 1 FROM shipment_free_time_overrides o
                     WHERE o.shipment_id = b.shipment_id AND o.fee_type IN ('DEM', 'DET')) THEN ARRAY['DEM', 'DET']
        WHEN EXISTS (SELECT 1 FROM rule_set rs
                     WHERE rs.container_id = b.container_id AND rs.fee_type = 'COMBINED') THEN ARRAY['COMBINED']
        ELSE ARRAY['DEM', 'DET'] END) AS k(fee_type)
), raw AS (
    SELECT b.*, k.fee_type, rs.rule_id,
           coalesce(o.free_days, rs.free_days) AS free_days,
           CASE WHEN o.free_days IS NOT NULL THEN 'OVERRIDE' WHEN rs.free_days IS NOT NULL THEN 'RULE'
                ELSE 'NONE' END AS rule_source,
           CASE k.fee_type WHEN 'DET' THEN b.gate_out_date ELSE b.discharged_date END AS start_date,
           CASE k.fee_type WHEN 'DEM' THEN b.gate_out_date ELSE b.returned_date END AS end_date
    FROM base b
    JOIN clocks k ON k.container_id = b.container_id
    LEFT JOIN shipment_free_time_overrides o ON o.shipment_id = b.shipment_id AND o.fee_type = k.fee_type
    LEFT JOIN rule_set rs ON rs.container_id = b.container_id AND rs.fee_type = k.fee_type
), staged AS (
    SELECT raw.*,
           CASE
               WHEN start_date IS NULL THEN
                   CASE WHEN fee_type IN ('DEM', 'COMBINED')
                             AND (eta < as_of OR shipment_status IN ('ARRIVED', 'CUSTOMS_CLEARING', 'CLEARED',
                                                                     'AT_WAREHOUSE', 'DELIVERING', 'COMPLETED'))
                        THEN 'MISSING_DATA' ELSE 'NOT_STARTED' END
               WHEN end_date IS NOT NULL THEN 'CLOSED'
               WHEN free_days IS NULL THEN 'NO_RULE'
               ELSE 'OPEN'
           END AS status,
           CASE WHEN start_date IS NOT NULL THEN greatest(coalesce(end_date, as_of) - start_date + 1, 0) END AS days_used
    FROM raw
), leveled AS (
    SELECT staged.*,
           CASE WHEN start_date IS NOT NULL AND free_days IS NOT NULL THEN start_date + free_days - 1 END AS due_date,
           CASE WHEN status = 'OPEN' THEN free_days - days_used END AS days_left,
           CASE WHEN status IN ('OPEN', 'CLOSED') AND free_days IS NOT NULL
                THEN greatest(days_used - free_days, 0) END AS days_over
    FROM staged
), scored AS (
    SELECT leveled.*,
           CASE status
               WHEN 'OPEN' THEN CASE WHEN days_left < 0 THEN 'RED' WHEN days_left <= 2 THEN 'YELLOW' ELSE 'GREEN' END
               WHEN 'NO_RULE' THEN 'NO_RULE'
               WHEN 'MISSING_DATA' THEN 'MISSING_DATA'
           END AS level
    FROM leveled
), priced AS (
    SELECT scored.*, fee.fee_amount, fee.fee_currency,
           max(freetime_level_rank(scored.level)) OVER (PARTITION BY scored.container_id) AS worst_rank
    FROM scored
    LEFT JOIN LATERAL (
        SELECT sum(t.rate_amount * greatest(0,
                   least(scored.days_used, coalesce(t.to_day, scored.days_used))
                   - greatest(CASE WHEN t.from_day = first_tier.from_day
                                   THEN least(t.from_day, scored.free_days + 1) ELSE t.from_day END,
                              scored.free_days + 1) + 1))::bigint AS fee_amount,
               max(t.currency)::text AS fee_currency
        FROM free_time_tiers t
        CROSS JOIN (SELECT min(from_day) AS from_day FROM free_time_tiers WHERE rule_id = scored.rule_id) first_tier
        WHERE t.rule_id = scored.rule_id
    ) fee ON scored.status IN ('OPEN', 'CLOSED') AND scored.free_days IS NOT NULL AND scored.rule_id IS NOT NULL
)
SELECT container_id, container_no, container_type, shipment_id, shipment_code, shipment_status, customer_name,
       carrier_name, pod_code, eta, fee_type, rule_source, status, level,
       CASE worst_rank WHEN 5 THEN 'RED' WHEN 4 THEN 'YELLOW' WHEN 3 THEN 'NO_RULE' WHEN 2 THEN 'MISSING_DATA'
                       WHEN 1 THEN 'GREEN' END AS container_level,
       discharged_date, gate_out_date, returned_date, start_date, end_date, free_days, due_date, days_used,
       days_left, days_over, fee_amount, fee_currency
FROM priced
ORDER BY container_id, fee_type
$$;

REVOKE ALL ON FUNCTION container_freetime(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION container_freetime(date) TO CURRENT_USER;
"""

COLUMN_COMMENTS = {
    "container_id": "Id container trong hệ thống",
    "container_no": "Số container (ISO 6346)",
    "container_type": "Loại container: 20GP, 40GP, 40HC, 45HC, 20RF, 40RF, 40RH",
    "shipment_id": "Id lô hàng",
    "shipment_code": "Mã lô nội bộ",
    "shipment_status": "Trạng thái lô: CREATED, IN_TRANSIT, ARRIVED, CUSTOMS_CLEARING, CLEARED, AT_WAREHOUSE, "
                       "DELIVERING, COMPLETED, CANCELLED",
    "customer_name": "Tên khách hàng của lô",
    "carrier_name": "Tên hãng tàu",
    "pod_code": "Mã UN/LOCODE cảng dỡ, ví dụ VNSGN",
    "eta": "Ngày dự kiến tàu đến",
    "fee_type": "Loại đồng hồ: DEM (lưu container tại cảng), DET (lưu vỏ), COMBINED (gộp DEM và DET)",
    "rule_source": "Nguồn số ngày free: OVERRIDE (ghi riêng cho lô), RULE (quy tắc chung của hãng tàu), NONE (không có)",
    "status": "Trạng thái đồng hồ: NOT_STARTED, OPEN, CLOSED, NO_RULE, MISSING_DATA",
    "level": "Mức cảnh báo của đồng hồ đang mở: GREEN (còn trên 2 ngày), YELLOW (còn 0 đến 2 ngày), RED (quá hạn), "
             "NO_RULE (chưa có quy tắc), MISSING_DATA (thiếu ngày dỡ hàng); rỗng khi NOT_STARTED hoặc CLOSED",
    "container_level": "Mức xấu nhất trong các đồng hồ của container: RED, YELLOW, NO_RULE, MISSING_DATA, GREEN",
    "discharged_date": "Ngày dỡ container khỏi tàu (giờ Việt Nam)",
    "gate_out_date": "Ngày lấy container đầy ra khỏi cảng (giờ Việt Nam)",
    "returned_date": "Ngày trả vỏ rỗng (giờ Việt Nam)",
    "start_date": "Ngày bắt đầu tính đồng hồ (tính cả ngày này)",
    "end_date": "Ngày kết thúc đồng hồ (tính cả ngày này); rỗng nếu đồng hồ chưa kết thúc",
    "free_days": "Số ngày free được hưởng",
    "due_date": "Ngày free cuối cùng; sau ngày này là quá hạn",
    "days_used": "Số ngày đã dùng, tính cả ngày đầu và ngày cuối",
    "days_left": "Số ngày free còn lại (âm nếu quá hạn); chỉ có khi đồng hồ đang mở",
    "days_over": "Số ngày quá hạn (0 nếu chưa quá hạn)",
    "fee_amount": "Phí ước tính theo bậc, đơn vị nhỏ nhất (USD là cent, VND là đồng); rỗng nếu chưa tính được",
    "fee_currency": "Tiền tệ của phí ước tính: USD hoặc VND",
}

VIEW = """
CREATE VIEW nlq.v_container_freetime AS SELECT * FROM container_freetime(nlq_today());
REVOKE ALL ON nlq.v_container_freetime FROM PUBLIC;
GRANT SELECT ON nlq.v_container_freetime TO CURRENT_USER;
"""


def upgrade() -> None:
    op.execute(TABLES)
    op.execute(HELPERS)
    op.execute(CLOCK_FUNCTION)
    op.execute(VIEW)
    for column, text in COLUMN_COMMENTS.items():
        op.execute(f"COMMENT ON COLUMN nlq.v_container_freetime.{column} IS '{text}'")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS nlq.v_container_freetime")
    op.execute("DROP FUNCTION IF EXISTS container_freetime(date)")
    op.execute("DROP VIEW IF EXISTS effective_container_milestones")
    op.execute("DROP FUNCTION IF EXISTS freetime_level_rank(text)")
    op.execute("DROP FUNCTION IF EXISTS nlq_today()")
    op.execute("DROP SCHEMA IF EXISTS nlq")
    op.execute("DROP TABLE shipment_free_time_overrides, free_time_tiers, free_time_rules")
