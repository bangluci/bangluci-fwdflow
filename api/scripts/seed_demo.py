"""Dữ liệu demo MÔ PHỎNG (không phải dữ liệu thật).

Chạy: python -m scripts.seed_demo [--seed N] [--size small|full] [--as-of YYYY-MM-DD] [--reset].
"""

import argparse
import sys
from datetime import date, datetime
from random import Random
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.service import hash_password, normalize_identifier
from app.catalog.models import Carrier, Customer, Driver, Port, Truck, Trucker, Warehouse
from app.config import get_settings
from app.db import SessionLocal
from scripts.seed_dataset import SIZES, build_dataset
from scripts.seed_writer import write_dataset

RESET_TABLES = ("users, sessions, login_attempts, audit_logs, customers, carriers, ports, "
                "warehouses, truckers, trucks, drivers")
MIN_PASSWORD_LEN = 10
VN = ZoneInfo("Asia/Ho_Chi_Minh")
DRIVER_LOGIN_PHONE = "0900000006"

CUSTOMERS = [
    ("Công ty TNHH Minh Long", "0312345671", "kh1@example.com"),
    ("Công ty CP Hải Âu Logistics", "0109876543", "kh2@example.com"),
    ("Công ty TNHH Đông Á Foods", "0401234567", None),
]
CARRIERS = [("MAEU", "Maersk"), ("REGU", "RCL (Regional Container Lines)"), ("ONEY", "Ocean Network Express")]
PORTS = [
    ("VNSGN", "Cát Lái, TP.HCM", ["VNCLI", "CAT LAI", "CATLAI", "TAN CANG CAT LAI"]),
    ("VNHPH", "Hải Phòng", ["HAI PHONG", "HAIPHONG", "DINH VU", "TAN VU"]),
    ("VNCMT", "Cái Mép", ["CAI MEP", "CAIMEP", "TCIT", "GEMALINK"]),
    ("CNSHA", "Thượng Hải", []),
    ("CNNGB", "Ninh Ba", []),
    ("KRPUS", "Busan", []),
    ("SGSIN", "Singapore", []),
]
DRIVER_NAMES = ["Nguyễn Văn Hùng", "Trần Quốc Bảo", "Lê Minh Tuấn", "Phạm Đức Long", "Võ Thanh Sơn", "Đặng Văn Khoa"]


def _accounts(customer_id: int, driver_id: int) -> list[tuple[str, dict]]:
    return [
        ("ADMIN", {"email": "admin@fwdflow.local", "full_name": "Quản trị viên"}),
        ("DOCS", {"email": "docs@fwdflow.local", "full_name": "Nhân viên chứng từ"}),
        ("DISPATCH", {"email": "dispatch@fwdflow.local", "full_name": "Điều độ viên"}),
        ("ACCOUNTANT", {"email": "accountant@fwdflow.local", "full_name": "Kế toán"}),
        ("CUSTOMER", {"email": "customer@fwdflow.local", "full_name": "Khách hàng demo", "customer_id": customer_id}),
        ("DRIVER", {"phone": DRIVER_LOGIN_PHONE, "full_name": "Tài xế demo", "driver_id": driver_id}),
    ]


def _seed_catalog(db: Session, rng: Random) -> tuple[int, int]:
    customers = [Customer(name=n, tax_code=tax, email=email) for n, tax, email in CUSTOMERS]
    db.add_all(customers)
    db.add_all([Carrier(code=c, name=n) for c, n in CARRIERS])
    db.add_all([Port(code=c, name=n, aliases=sorted(a)) for c, n, a in PORTS])
    db.flush()
    db.add_all([
        Warehouse(name="Kho FwdFlow Bình Tân", address="KCN Tân Tạo, Bình Tân, TP.HCM"),
        Warehouse(name="Kho FwdFlow Hải Phòng", address="KCN Đình Vũ, Hải Phòng"),
        Warehouse(name="Kho Minh Long", address="KCN Tân Bình, TP.HCM", customer_id=customers[0].id),
    ])
    names = rng.sample(DRIVER_NAMES, 4)
    first_driver_id = 0
    for t, trucker_name in enumerate(["Đội xe FwdFlow", "Vận tải Thành Đạt"]):
        trucker = Trucker(name=trucker_name)
        db.add(trucker)
        db.flush()
        for k in range(2):
            plate = f"{rng.choice([50, 51, 15, 29])}C-{rng.randint(10000, 99999)}"
            db.add(Truck(trucker_id=trucker.id, plate_no=plate))
            phone = DRIVER_LOGIN_PHONE if t == 0 and k == 0 else f"09{rng.randint(10000000, 99999999)}"
            driver = Driver(trucker_id=trucker.id, full_name=names[t * 2 + k], phone=phone)
            db.add(driver)
            db.flush()
            first_driver_id = first_driver_id or driver.id
    return customers[0].id, first_driver_id


def seed(db: Session, seed_value: int, *, password: str) -> list[tuple[str, str]]:
    """Tạo danh mục + 6 tài khoản (mỗi vai trò một); trả về (vai trò, email / SĐT đăng nhập). Không ghi audit."""
    customer_id, driver_id = _seed_catalog(db, Random(seed_value))  # noqa: S311 - dữ liệu demo, không phải bí mật
    password_hash = hash_password(password)
    accounts = []
    for role, fields in _accounts(customer_id, driver_id):
        user = User(role=role, password_hash=password_hash, **fields)
        db.add(user)
        accounts.append((role, normalize_identifier(fields.get("email") or fields["phone"])))
    db.flush()
    return accounts


def run(db: Session, *, seed_value: int, reset: bool, env: str, password: str, size: str | None = None,
        as_of: date | None = None) -> int:
    if env == "prod":
        print("seed_demo không chạy ở prod")
        return 1
    if len(password) < MIN_PASSWORD_LEN:
        print(f"Đặt SEED_PASSWORD trong .env (≥ {MIN_PASSWORD_LEN} ký tự)")
        return 1
    if reset:
        db.execute(text(f"TRUNCATE {RESET_TABLES} RESTART IDENTITY CASCADE"))
    elif db.scalar(select(User.id).limit(1)) is not None:
        print("DB đã có dữ liệu, dùng --reset")
        return 1
    for role, identifier in seed(db, seed_value, password=password):
        print(f"{role}\t{identifier}")
    if size:
        counts = write_dataset(db, build_dataset(seed_value, size, as_of or datetime.now(VN).date()))
        print(f"driver1: {counts['driver_orders']} lệnh")
        print(f"shipments={counts['shipments']} containers={counts['containers']} "
              f"last_mile_orders={counts['last_mile_orders']} charges={counts['charges']}")
    db.commit()
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # in tiếng Việt được cả khi Windows pipe ra file
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--size", choices=sorted(SIZES), default="small", help="quy mô dữ liệu nghiệp vụ")
    parser.add_argument("--as-of", type=date.fromisoformat, help="ngày tham chiếu YYYY-MM-DD (mặc định hôm nay)")
    parser.add_argument("--reset", action="store_true", help="xoá dữ liệu cũ trước khi seed")
    args = parser.parse_args(argv)
    settings = get_settings()
    with SessionLocal() as db:
        return run(db, seed_value=args.seed, reset=args.reset, env=settings.app_env, password=settings.seed_password,
                   size=args.size, as_of=args.as_of or settings.app_today)


if __name__ == "__main__":
    sys.exit(main())
