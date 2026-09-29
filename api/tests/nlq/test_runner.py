"""run_readonly: kết nối riêng, chỉ đọc, có trần thời gian và số dòng, chặn ghi ở tầng role."""

import time

import pytest
from sqlalchemy import text

from app.ai.nlq.runner import NlqExecError, NlqTimeout, run_readonly
from app.config import get_settings
from tests.nlq.test_guard import ADVERSARIAL_SQL

TEST_URL = get_settings().database_url_test

# Chuỗi ghi hoặc đọc bảng gốc (bỏ qua validator): role phải tự chặn ở Postgres
WRITE_OR_BASE_TABLE_SQL = [
    sql for sql in ADVERSARIAL_SQL
    if sql.startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER", "CREATE", "GRANT", "COPY", "DEL/**/"))
    or "public.shipments" in sql or '"public"."users"' in sql or sql == "SELECT * FROM customers"
    or sql.startswith(("WITH x AS (DELETE", "WITH x AS (INSERT", "WITH x AS (UPDATE", "SELECT * INTO"))
]


def _customers(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM customers")).scalar()


def test_as_of_applied():
    result = run_readonly("SELECT nlq_today()", "nlq_ops", "2026-12-15", TEST_URL)
    assert result.columns == ["nlq_today"] and result.rows == [["2026-12-15"]] and result.truncated is False


def test_statement_timeout_5s():
    started = time.monotonic()
    with pytest.raises(NlqTimeout):
        run_readonly("select count(*) from generate_series(1, 10000000000)", "nlq_ops", "2026-12-15", TEST_URL)
    assert time.monotonic() - started < 7


def test_truncated_over_500():
    result = run_readonly("select generate_series(1, 600) as n", "nlq_ops", "2026-12-15", TEST_URL)
    assert len(result.rows) == 500 and result.truncated is True and result.rows[-1] == [500]


def test_exactly_500_rows_is_not_truncated():
    result = run_readonly("select generate_series(1, 500) as n", "nlq_ops", "2026-12-15", TEST_URL)
    assert len(result.rows) == 500 and result.truncated is False


def test_exec_error_raised():
    with pytest.raises(NlqExecError) as err:
        run_readonly("SELECT khong_co_cot FROM nlq.v_shipments", "nlq_ops", "2026-12-15", TEST_URL)
    assert "khong_co_cot" in str(err.value)


def test_values_are_json_safe():
    result = run_readonly("SELECT 12.50::numeric AS a, 3::numeric AS b, DATE '2026-12-15' AS c, "
                          "TIMESTAMPTZ '2026-12-15 08:00+07' AS d, NULL AS e", "nlq_ops", "2026-12-15", TEST_URL)
    assert result.rows == [[12.5, 3, "2026-12-15", "2026-12-15T01:00:00+00:00", None]]


def test_percent_signs_in_like_are_not_placeholders():
    result = run_readonly("SELECT 'abc' LIKE '%b%' AS ok", "nlq_ops", "2026-12-15", TEST_URL)
    assert result.rows == [[True]]


def test_ops_role_cannot_read_finance_view():
    with pytest.raises(NlqExecError) as err:
        run_readonly("SELECT * FROM nlq.v_charges", "nlq_ops", "2026-12-15", TEST_URL)
    assert "permission denied" in str(err.value)
    run_readonly("SELECT * FROM nlq.v_charges", "nlq_finance", "2026-12-15", TEST_URL)


def test_transaction_is_read_only():
    with pytest.raises(NlqExecError) as err:
        run_readonly("CREATE TEMP TABLE t AS SELECT 1", "nlq_ops", "2026-12-15", TEST_URL)
    assert "read-only" in str(err.value)


def test_unknown_role_is_refused():
    with pytest.raises(ValueError):
        run_readonly("SELECT 1", "postgres", "2026-12-15", TEST_URL)


def test_write_list_has_enough_cases():
    assert len(WRITE_OR_BASE_TABLE_SQL) >= 15


@pytest.mark.parametrize("sql", WRITE_OR_BASE_TABLE_SQL)
def test_adversarial_sql_blocked_by_role(engine, one_committed_customer, sql):
    before = _customers(engine)
    with pytest.raises(NlqExecError):
        run_readonly(sql, "nlq_finance", "2026-12-15", TEST_URL)
    assert _customers(engine) == before == 1
