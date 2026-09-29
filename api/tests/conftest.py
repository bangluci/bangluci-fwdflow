"""Harness test: Postgres thật (DATABASE_URL_TEST), migrate head một lần, rollback sau mỗi test."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.service import create_session, hash_password
from app.catalog.models import Customer, Driver, Trucker
from app.config import get_settings
from app.db import get_db
from app.main import app

pytest_plugins = ["tests.shipment_factories", "tests.extraction_factories", "tests.freetime_factories",
                  "tests.trucking_factories", "tests.driver_factories"]

API_DIR = Path(__file__).resolve().parents[1]


def _alembic_config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.attributes["url"] = url
    cfg.attributes["skip_logging"] = True
    return cfg


@pytest.fixture(scope="session")
def engine():
    url = get_settings().database_url_test
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS nlq CASCADE"))
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(_alembic_config(url), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    conn = engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    outer.rollback()
    conn.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, base_url="https://testserver") as c:
        yield c
    app.dependency_overrides.clear()


TEST_PASSWORD = "Mat-khau-test-123"


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    """Mọi test ghi file upload vào thư mục tạm, không đụng data/files của repo."""
    target = tmp_path / "files"
    monkeypatch.setattr(get_settings(), "files_dir", target)
    return target


@pytest.fixture
def make_user(db):
    """Tạo user theo vai trò (tự tạo khách hàng / tài xế liên kết khi cần)."""
    counter = iter(range(1, 10_000))

    def _make(role: str = "ADMIN", **kw) -> User:
        n = next(counter)
        if role == "CUSTOMER" and "customer_id" not in kw:
            customer = Customer(name=f"Khach {n}")
            db.add(customer)
            db.flush()
            kw["customer_id"] = customer.id
        if role == "DRIVER" and "driver_id" not in kw:
            trucker = Trucker(name=f"Nha xe {n}")
            db.add(trucker)
            db.flush()
            driver = Driver(trucker_id=trucker.id, full_name=f"Tai xe {n}")
            db.add(driver)
            db.flush()
            kw["driver_id"] = driver.id
        user = User(
            email=kw.pop("email", f"{role.lower()}{n}@test.local"),
            full_name=kw.pop("full_name", f"{role} {n}"),
            role=role,
            password_hash=hash_password(TEST_PASSWORD),
            **kw,
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def login_as(client, db, make_user):
    """login_as("DOCS") → user; client mang cookie phiên của user đó."""

    def _login(role: str = "ADMIN", **kw) -> User:
        user = make_user(role, **kw)
        token = create_session(db, user, "127.0.0.1", "pytest")
        db.flush()
        client.cookies.set(get_settings().session_cookie_name, token)
        return user

    return _login
