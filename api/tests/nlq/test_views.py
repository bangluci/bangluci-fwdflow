"""View nlq.*, hàm che tên, quyền của hai role đọc và bảng nhật ký câu hỏi (migration 0012)."""

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.ai.nlq.models import NlQueryLog
from app.lastmile.public_router import mask_name
from tests.nlq.factories import make_charge

VIEWS = ("v_shipments", "v_trucking", "v_last_mile", "v_charges", "v_container_freetime")
OPS_VIEWS = {"v_shipments", "v_trucking", "v_last_mile", "v_container_freetime"}


def _columns(db, view: str) -> list[str]:
    return list(db.scalars(text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'nlq' "
                                "AND table_name = :v ORDER BY ordinal_position"), {"v": view}))


def test_nlq_views_exist(db):
    found = set(db.scalars(text("SELECT table_name FROM information_schema.views WHERE table_schema = 'nlq'")))
    assert set(VIEWS) <= found


@pytest.mark.parametrize("view", VIEWS)
def test_views_have_no_pii_columns(db, view):
    bad = [c for c in _columns(db, view) if any(word in c for word in ("phone", "address", "tax", "tracking"))]
    assert bad == []


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_column_has_comment(db, view):
    missing = db.scalars(text(
        "SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'nlq' AND c.relname = :v AND a.attnum > 0 AND NOT a.attisdropped "
        "AND coalesce(col_description(c.oid, a.attnum), '') = ''"), {"v": view}).all()
    assert missing == []


def test_recipient_masked_matches_public_track(db, make_shipment, make_last_mile_order):
    shipment = make_shipment(status="AT_WAREHOUSE", delivery_mode="VIA_WAREHOUSE")
    order = make_last_mile_order(shipment, recipient_name="Nguyễn Văn An", events=("CREATED",))
    masked = db.scalar(text("SELECT recipient_masked FROM nlq.v_last_mile WHERE shipment_code = :c"),
                       {"c": shipment.code})
    assert masked == mask_name(order.recipient_name) == "N*** V*** A***"


@pytest.mark.parametrize("name", ["Nguyễn Văn An", "  Trần  Thị Bích ", "Đặng", "Lê Ô Uy Tín"])
def test_sql_mask_name_equals_python(db, name):
    assert db.scalar(text("SELECT nlq.mask_name(:n)"), {"n": name}) == mask_name(name)


def test_charges_view_uses_major_units(db, make_shipment):
    shipment = make_shipment()
    make_charge(db, shipment, currency="USD", amount=12_345, fx_rate="25000")
    make_charge(db, shipment, currency="VND", amount=2_500_000)
    rows = dict(db.execute(text("SELECT currency, amount FROM nlq.v_charges WHERE shipment_code = :c"),
                           {"c": shipment.code}).all())
    assert float(rows["USD"]) == 123.45 and float(rows["VND"]) == 2_500_000


def test_shipments_view_counts_containers_and_completion(db, make_shipment, make_container):
    shipment = make_shipment(status="CREATED")
    make_container(shipment)
    make_container(shipment)
    row = db.execute(text("SELECT container_count, completed_at, staff_name FROM nlq.v_shipments "
                          "WHERE shipment_code = :c"), {"c": shipment.code}).one()
    assert row.container_count == 2 and row.completed_at is None and row.staff_name


def test_nl_query_log_roundtrip(db, make_user):
    user = make_user("ACCOUNTANT")
    log = NlQueryLog(user_id=user.id, nlq_role="nlq_finance", question="Tổng doanh thu tháng này?",
                     sql_generated="select 1", sql_final="SELECT 1 LIMIT 501", validation_result="OK", error_code=None,
                     repaired=True, row_count=1, truncated=False, answer_checked=True, user_rating=None,
                     usage={"input_tokens": 10}, latency_ms=250)
    db.add(log)
    db.flush()
    db.expire(log)
    saved = db.get(NlQueryLog, log.id)
    assert (saved.nlq_role, saved.question, saved.repaired, saved.answer_checked, saved.usage) == (
        "nlq_finance", "Tổng doanh thu tháng này?", True, True, {"input_tokens": 10})
    assert saved.created_at is not None and saved.user_rating is None


@pytest.mark.parametrize("role", ["nlq_ops", "nlq_finance"])
@pytest.mark.parametrize("view", VIEWS)
def test_role_view_access(db, role, view):
    db.execute(text(f"SET LOCAL ROLE {role}"))
    if view in OPS_VIEWS or role == "nlq_finance":
        db.execute(text(f"SELECT * FROM nlq.{view} LIMIT 1"))  # noqa: S608 - view lấy từ hằng số của test
        return
    with pytest.raises(DBAPIError) as err:
        db.execute(text(f"SELECT * FROM nlq.{view} LIMIT 1"))  # noqa: S608 - view lấy từ hằng số của test
    assert isinstance(err.value.orig, psycopg.errors.InsufficientPrivilege)


def test_nlq_role_is_read_only(db):
    db.execute(text("SET LOCAL ROLE nlq_finance"))
    with pytest.raises(DBAPIError) as err:
        db.execute(text("INSERT INTO customers (name) VALUES ('x')"))
    assert isinstance(err.value.orig, psycopg.errors.InsufficientPrivilege)


def test_roles_cannot_read_base_tables(db):
    db.execute(text("SET LOCAL ROLE nlq_ops"))
    with pytest.raises(DBAPIError) as err:
        db.execute(text("SELECT * FROM customers LIMIT 1"))
    assert isinstance(err.value.orig, psycopg.errors.InsufficientPrivilege)


def test_role_attributes_are_locked_down(db):
    rows = db.execute(text("SELECT rolname, rolsuper, rolinherit, rolcreatedb, rolcreaterole, rolcanlogin "
                           "FROM pg_roles WHERE rolname IN ('nlq_ops', 'nlq_finance')")).all()
    assert len(rows) == 2
    assert all((r.rolsuper, r.rolinherit, r.rolcreatedb, r.rolcreaterole, r.rolcanlogin) ==
               (False, False, False, False, True) for r in rows)
