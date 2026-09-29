"""validate_sql: chuỗi đối kháng phải bị từ chối, câu hỏi thật phải qua và được chuẩn hoá."""

import pytest

from app.ai.nlq.validate_sql import (
    ALLOWED_FUNCTIONS,
    FINANCE_VIEWS,
    OPS_VIEWS,
    SqlForbiddenView,
    SqlRejected,
    validate_sql,
)

ADVERSARIAL_SQL = [
    # nhiều câu, ghi dữ liệu, DDL
    "SELECT 1; SELECT 2",
    "SELECT * FROM nlq.v_shipments; DROP TABLE customers",
    "WITH x AS (DELETE FROM charges RETURNING *) SELECT * FROM x",
    "WITH x AS (INSERT INTO customers (name) VALUES ('a') RETURNING *) SELECT * FROM x",
    "WITH x AS (UPDATE charges SET amount = 0 RETURNING *) SELECT * FROM x",
    "SELECT * INTO newtable FROM nlq.v_shipments",
    "INSERT INTO charges VALUES (1)",
    "UPDATE charges SET amount = 0",
    "DELETE FROM charges",
    "TRUNCATE charges",
    "DROP TABLE charges",
    "ALTER TABLE charges ADD COLUMN x int",
    "CREATE TABLE t AS SELECT 1",
    "CREATE VIEW v AS SELECT 1",
    "GRANT ALL ON charges TO PUBLIC",
    "DEL/**/ETE FROM charges",
    "COPY charges TO STDOUT",
    "CALL do_something()",
    "DO $$ BEGIN PERFORM 1; END $$",
    "SET ROLE postgres",
    "RESET ALL",
    "SHOW all",
    "EXPLAIN ANALYZE SELECT 1",
    "VACUUM",
    # khoá dòng
    "SELECT * FROM nlq.v_shipments FOR UPDATE",
    "SELECT * FROM nlq.v_shipments FOR SHARE",
    # hàm nguy hiểm hoặc ngoài danh sách trắng
    "SELECT query_to_xml('select 1', true, true, '')",
    "SELECT * FROM dblink('host=x', 'select 1') AS t(a int)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT lo_export(1, '/tmp/x')",
    "SELECT set_config('app.as_of', '2020-01-01', false)",
    "SELECT pg_sleep(10)",
    "SELECT (SELECT pg_sleep(5))",
    "SELECT pg_ls_dir('.')",
    "SELECT txid_current()",
    "SELECT version()",
    "SELECT current_user",
    "SELECT session_user",
    "SELECT statement_timestamp()",
    "SELECT * FROM generate_series(1, 100000000)",
    "SELECT * FROM unnest(ARRAY[1, 2, 3])",
    "SELECT 1 UNION SELECT pg_sleep(1)",
    # ngày giờ không cố định (kết quả phải theo as_of qua nlq_today())
    "SELECT current_date",
    "SELECT now()",
    "SELECT CURRENT_TIMESTAMP",
    "SELECT LOCALTIMESTAMP",
    # bảng ngoài schema nlq
    "SELECT * FROM public.shipments",
    'SELECT * FROM "public"."users"',
    "SELECT * FROM pg_catalog.pg_roles",
    "SELECT * FROM pg_stat_activity",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM nlq.v_shipments AS a, public.customers AS b",
    "SELECT * FROM nlq.v_shipments t JOIN (SELECT * FROM users) u ON true",
    "SELECT * FROM nlq.v_shipments WHERE shipment_code IN (SELECT rolname FROM pg_roles)",
    "SELECT * FROM customers",
    'SELECT * FROM "Nlq"."V_Shipments"',
    "SELECT * FROM otherdb.nlq.v_shipments",
    # kiểu ép, tham số, đệ quy, FETCH
    "SELECT 'pg_roles'::regclass",
    "SELECT * FROM nlq.v_shipments WHERE shipment_code = $1",
    "SELECT * FROM nlq.v_shipments WHERE shipment_code = :code",
    "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t) SELECT * FROM t",
    "SELECT * FROM nlq.v_shipments FETCH FIRST 5 ROWS ONLY",
    # view có thật nhưng ngoài quyền của role ops
    "SELECT * FROM nlq.v_charges",
    "SELECT sum(amount_vnd) FROM v_charges",
    "SELECT * FROM nlq.v_shipments s JOIN nlq.v_charges c ON c.shipment_code = s.shipment_code",
    # rác
    "",
    "   ",
    "SELEC * FRM x",
    "SELECT " + "1," * 3000 + "1",
]

VALID_SQL = [
    "SELECT status, count(*) AS n FROM nlq.v_shipments GROUP BY status ORDER BY n DESC",
    "SELECT customer_name, count(*) FROM v_shipments WHERE created_at >= date_trunc('month', nlq_today()) GROUP BY 1",
    "SELECT shipment_code, days_over FROM nlq.v_container_freetime WHERE level = 'RED' ORDER BY days_over DESC LIMIT 20",
    "SELECT extract(month FROM created_at) AS thang, round(avg(container_count), 1) FROM nlq.v_shipments GROUP BY 1",
    "SELECT to_char(delivered_at, 'YYYY-MM') AS thang, sum(packages) FROM nlq.v_last_mile WHERE status = 'DELIVERED' GROUP BY 1",
    "SELECT driver_name, count(*) FILTER (WHERE status = 'FAILED') AS that_bai FROM nlq.v_last_mile GROUP BY driver_name",
    "SELECT shipment_code, CASE WHEN eta < nlq_today() THEN 'tre' ELSE 'dung han' END FROM nlq.v_shipments",
    "SELECT shipment_code, row_number() OVER (PARTITION BY customer_name ORDER BY created_at) FROM nlq.v_shipments",
    "SELECT shipment_code FROM nlq.v_shipments WHERE eta::date > nlq_today() - INTERVAL '7 days'",
    "WITH busy AS (SELECT customer_name, count(*) n FROM nlq.v_shipments GROUP BY 1) SELECT * FROM busy WHERE n > 3",
    "SELECT shipment_code FROM nlq.v_trucking UNION SELECT shipment_code FROM nlq.v_last_mile",
    "SELECT coalesce(sum(amount_vnd), 0) FROM nlq.v_charges WHERE direction = 'REVENUE' AND category = 'DEM'",
]


@pytest.mark.parametrize("sql", ADVERSARIAL_SQL)
def test_adversarial_sql_rejected(sql):
    with pytest.raises(SqlRejected):
        validate_sql(sql, OPS_VIEWS)


def test_adversarial_list_is_large_enough():
    assert len(ADVERSARIAL_SQL) >= 50


def test_finance_view_forbidden_for_ops():
    with pytest.raises(SqlForbiddenView) as err:
        validate_sql("SELECT * FROM nlq.v_charges", OPS_VIEWS)
    assert err.value.view == "v_charges"
    validate_sql("SELECT * FROM nlq.v_charges", FINANCE_VIEWS)


def test_forbidden_view_inside_cte_or_subquery_is_still_caught():
    sql = "WITH x AS (SELECT amount_vnd FROM nlq.v_charges) SELECT * FROM x"
    with pytest.raises(SqlForbiddenView):
        validate_sql(sql, OPS_VIEWS)
    with pytest.raises(SqlForbiddenView):
        validate_sql("SELECT * FROM nlq.v_shipments WHERE 1 IN (SELECT amount_vnd FROM nlq.v_charges)", OPS_VIEWS)


@pytest.mark.parametrize("sql", VALID_SQL)
def test_valid_queries_pass(sql):
    out = validate_sql(sql, FINANCE_VIEWS)
    assert out.upper().startswith(("SELECT", "WITH")) and ";" not in out


def test_limit_forced_to_501():
    assert validate_sql("SELECT * FROM nlq.v_shipments", OPS_VIEWS).endswith("LIMIT 501")
    assert validate_sql("SELECT * FROM nlq.v_shipments LIMIT 1000", OPS_VIEWS).endswith("LIMIT 501")
    assert validate_sql("SELECT * FROM nlq.v_shipments LIMIT 10", OPS_VIEWS).endswith("LIMIT 10")
    assert validate_sql("SELECT * FROM nlq.v_shipments LIMIT 500", OPS_VIEWS).endswith("LIMIT 500")
    union = validate_sql("SELECT shipment_code FROM nlq.v_trucking UNION SELECT shipment_code FROM nlq.v_last_mile",
                         OPS_VIEWS)
    assert union.endswith("LIMIT 501")


def test_valid_join_passes_and_tables_get_schema():
    sql = ("SELECT s.shipment_code, count(*) FROM v_shipments s JOIN nlq.v_trucking t "
           "ON t.shipment_code = s.shipment_code GROUP BY 1")
    out = validate_sql(sql, OPS_VIEWS)
    assert "nlq.v_shipments AS s" in out and "nlq.v_trucking AS t" in out


def test_comments_stripped():
    out = validate_sql("SELECT shipment_code /* pg_sleep(9) */ FROM nlq.v_shipments -- drop table x", OPS_VIEWS)
    assert "/*" not in out and "--" not in out and "pg_sleep" not in out


def test_uppercase_unquoted_names_are_lowercased_like_postgres():
    assert "nlq.v_shipments" in validate_sql("SELECT * FROM NLQ.V_SHIPMENTS", OPS_VIEWS)


def test_allowed_functions_are_the_documented_whitelist():
    assert {"count", "nlq_today", "date_trunc"} <= ALLOWED_FUNCTIONS
    assert not {"now", "pg_sleep", "set_config", "current_date"} & ALLOWED_FUNCTIONS
