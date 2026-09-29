from sqlalchemy import select

from app.auth.models import User
from app.catalog.models import Port, Truck
from scripts.seed_demo import run, seed
from tests.conftest import TEST_PASSWORD


def _run(db, **overrides):
    return run(db, **{"seed_value": 1, "reset": False, "env": "dev", "password": TEST_PASSWORD, **overrides})


def test_seed_creates_six_roles_and_vn_ports(db):
    accounts = seed(db, 1, password=TEST_PASSWORD)
    assert sorted(role for role, _ in accounts) == ["ACCOUNTANT", "ADMIN", "CUSTOMER", "DISPATCH", "DOCS", "DRIVER"]
    assert ("DRIVER", "0900000006") in accounts
    port = db.scalar(select(Port).where(Port.aliases.any("CAT LAI")))
    assert port.code == "VNSGN"


def test_seeded_admin_can_login(client, db):
    seed(db, 1, password=TEST_PASSWORD)
    res = client.post("/api/auth/login", json={"identifier": "admin@fwdflow.local", "password": TEST_PASSWORD})
    assert res.status_code == 200 and res.json()["data"]["role"] == "ADMIN"


def test_seed_plates_follow_seed_value(db):
    def plates(seed_value):
        run(db, seed_value=seed_value, reset=True, env="dev", password=TEST_PASSWORD)
        return sorted(db.scalars(select(Truck.plate_no)))

    assert plates(7) == plates(7) != plates(8)


def test_seed_refuses_non_empty_without_reset(db, capsys):
    seed(db, 1, password=TEST_PASSWORD)
    assert _run(db) == 1
    assert "dùng --reset" in capsys.readouterr().out


def test_seed_refuses_in_prod(db, capsys):
    assert _run(db, env="prod") == 1
    assert "không chạy ở prod" in capsys.readouterr().out
    assert db.scalar(select(User.id).limit(1)) is None


def test_seed_refuses_short_password(db, capsys):
    assert _run(db, password="ngan") == 1
    assert "SEED_PASSWORD" in capsys.readouterr().out


def test_reset_replaces_existing_data(db):
    seed(db, 1, password=TEST_PASSWORD)
    assert _run(db, reset=True, seed_value=2) == 0
    assert len(db.scalars(select(User)).all()) == 6
