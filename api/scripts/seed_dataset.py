"""Dựng bộ dữ liệu demo MÔ PHỎNG: hàm thuần `build_dataset`, chỉ dùng `random.Random(seed)`, mọi mốc lùi từ `as_of`.

Mỗi lô đi theo một kịch bản cố định (20 kịch bản xoay vòng) để chắc chắn phủ đủ trạng thái, đồng hồ free time,
D/O sắp hết hạn, đơn giao đủ trạng thái, rồi mới điền ngẫu nhiên phần còn lại. Không ghi DB ở đây.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from random import Random
from zoneinfo import ZoneInfo

from app.lastmile.tracking_code import ALPHABET
from app.shipments.iso6346 import container_check_digit

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SIZES = {"small": {"shipments": 20, "containers": 50, "orders": 200},
         "full": {"shipments": 200, "containers": 500, "orders": 2000}}
CUSTOMER_COUNT, DRIVER_COUNT = 3, 4
COMPANIES = ["Công ty TNHH Minh Long", "Công ty CP Hải Âu Logistics", "Công ty TNHH Đông Á Foods"]
RECIPIENTS = ["Nguyễn Văn An", "Trần Thị Bình", "Lê Hoàng Cường", "Phạm Thu Dung", "Võ Quang Huy", "Đặng Mai Lan",
              "Bùi Minh Khoa", "Hoàng Ngọc Yến"]
STREETS = ["Lê Lợi", "Nguyễn Trãi", "Trần Hưng Đạo", "Hai Bà Trưng", "Phan Văn Trị", "Cách Mạng Tháng 8"]
DISTRICTS = ["Quận 1", "Quận 3", "Quận 5", "Bình Thạnh", "Tân Bình", "Thủ Đức", "Bình Tân", "Gò Vấp"]
STATUS_ORDER = ["CREATED", "IN_TRANSIT", "ARRIVED", "CUSTOMS_CLEARING", "CLEARED", "AT_WAREHOUSE", "DELIVERING",
                "COMPLETED"]
DOC_RULES = [("IN_TRANSIT", "HBL"), ("IN_TRANSIT", "INVOICE"), ("IN_TRANSIT", "PACKING_LIST"),
             ("ARRIVED", "ARRIVAL_NOTICE"), ("CLEARED", "CUSTOMS_DECLARATION"), ("CLEARED", "DO")]


@dataclass(frozen=True)
class Scenario:
    status: str
    load_type: str
    delivery_mode: str
    carrier: str  # mã hãng tàu; ONEY không có quy tắc free time
    customer: int
    age: int | None  # số ngày từ lúc dỡ hàng tới as_of (None: chưa ghi nhận dỡ hàng)
    do_expiring: bool = False
    fta: bool = False


# 20 kịch bản xoay vòng: 4 LCL, 3 giao tới cửa (CONTAINER_TO_DOOR), 7 lô VIA_WAREHOUSE có đơn giao
SCENARIOS = [
    Scenario("CREATED", "FCL", "VIA_WAREHOUSE", "MAEU", 0, None),
    Scenario("CREATED", "LCL", "VIA_WAREHOUSE", "REGU", 1, None),
    Scenario("IN_TRANSIT", "FCL", "VIA_WAREHOUSE", "MAEU", 2, None),
    Scenario("IN_TRANSIT", "FCL", "CONTAINER_TO_DOOR", "REGU", 0, None),
    Scenario("ARRIVED", "FCL", "VIA_WAREHOUSE", "ONEY", 1, 3),
    Scenario("ARRIVED", "FCL", "VIA_WAREHOUSE", "REGU", 0, None),
    Scenario("ARRIVED", "FCL", "VIA_WAREHOUSE", "REGU", 0, 9),
    Scenario("CUSTOMS_CLEARING", "FCL", "VIA_WAREHOUSE", "REGU", 1, 3, fta=True),
    Scenario("CUSTOMS_CLEARING", "FCL", "CONTAINER_TO_DOOR", "MAEU", 2, 1),
    Scenario("CLEARED", "FCL", "VIA_WAREHOUSE", "REGU", 0, 8, do_expiring=True),
    Scenario("CLEARED", "FCL", "VIA_WAREHOUSE", "MAEU", 1, 4, fta=True),
    Scenario("AT_WAREHOUSE", "FCL", "VIA_WAREHOUSE", "MAEU", 0, 7),
    Scenario("AT_WAREHOUSE", "LCL", "VIA_WAREHOUSE", "REGU", 1, 6),
    Scenario("DELIVERING", "FCL", "VIA_WAREHOUSE", "MAEU", 0, 9),
    Scenario("DELIVERING", "LCL", "VIA_WAREHOUSE", "REGU", 2, 8),
    Scenario("COMPLETED", "FCL", "VIA_WAREHOUSE", "MAEU", 1, 16),
    Scenario("COMPLETED", "LCL", "VIA_WAREHOUSE", "REGU", 0, 14),
    Scenario("COMPLETED", "FCL", "CONTAINER_TO_DOOR", "REGU", 2, 15),
    Scenario("AT_WAREHOUSE", "FCL", "VIA_WAREHOUSE", "REGU", 1, 12),
    Scenario("CANCELLED", "FCL", "VIA_WAREHOUSE", "MAEU", 0, None),
]
FORCED_ORDERS = {  # các đơn đầu của lô có trạng thái cố định để chắc chắn phủ đủ trường hợp
    "AT_WAREHOUSE": ["CREATED", "ASSIGNED", "CANCELLED"],
    "DELIVERING": ["PICKED_UP", "ASSIGNED", "DELIVERED", "FAILED", "RETURNED"],
    "COMPLETED": ["DELIVERED", "RETURNED", "CANCELLED"],
}
ORDER_MIX = {  # tỉ lệ đơn theo trạng thái của lô (đơn nào cũng phải khớp với trạng thái tự chuyển của lô)
    "AT_WAREHOUSE": [("CREATED", 5), ("ASSIGNED", 4), ("CANCELLED", 1)],
    "DELIVERING": [("DELIVERED", 4), ("PICKED_UP", 2), ("FAILED", 1), ("ASSIGNED", 2), ("CREATED", 1),
                   ("RETURNED", 1)],
    "COMPLETED": [("DELIVERED", 16), ("RETURNED", 1), ("CANCELLED", 1)],
}
EVENTS_OF = {  # chuỗi event của đơn giao theo trạng thái cuối
    "CREATED": ("CREATED",), "ASSIGNED": ("CREATED", "ASSIGNED"),
    "PICKED_UP": ("CREATED", "ASSIGNED", "PICKED_UP"), "DELIVERED": ("CREATED", "ASSIGNED", "PICKED_UP", "DELIVERED"),
    "FAILED": ("CREATED", "ASSIGNED", "PICKED_UP", "FAILED"),
    "RETURNED": ("CREATED", "ASSIGNED", "PICKED_UP", "FAILED", "RETURNED"), "CANCELLED": ("CREATED", "CANCELLED"),
}


@dataclass(frozen=True)
class ContainerPlan:
    container_no: str
    container_type: str
    discharged: datetime | None
    gate_out: datetime | None
    returned: datetime | None


@dataclass(frozen=True)
class TruckingPlan:
    container_index: int
    kind: str
    planned_at: datetime
    events: tuple[tuple[str, datetime], ...]  # (loại, thời điểm)


@dataclass(frozen=True)
class OrderPlan:
    tracking_code: str
    recipient_name: str
    recipient_phone: str
    address: str
    packages: int
    planned_date: date
    driver_index: int | None
    events: tuple[tuple[str, datetime], ...]
    status: str


@dataclass(frozen=True)
class ChargePlan:
    direction: str
    category: str
    amount: int
    currency: str
    fx_rate: int | None
    charge_date: date


@dataclass(frozen=True)
class ShipmentPlan:
    scenario: Scenario
    carrier: str
    pol: str
    pod: str
    etd: date
    eta: date
    total_packages: int
    do_valid_until: date | None
    transitions: tuple[tuple[str, datetime, bool], ...]  # (trạng thái, thời điểm, do hệ thống tự chuyển)
    containers: tuple[ContainerPlan, ...]
    declaration: tuple[str, datetime, datetime | None] | None  # (số tờ khai, đăng ký, thông quan)
    documents: tuple[str, ...]
    trucking: tuple[TruckingPlan, ...]
    orders: tuple[OrderPlan, ...]
    charges: tuple[ChargePlan, ...]


@dataclass(frozen=True)
class Dataset:
    seed: int
    size: str
    as_of: date
    shipments: tuple[ShipmentPlan, ...]

    @property
    def container_count(self) -> int:
        return sum(len(s.containers) for s in self.shipments)

    @property
    def order_count(self) -> int:
        return sum(len(s.orders) for s in self.shipments)


def vn(day: date, hour: int, minute: int = 0) -> datetime:
    """Giờ Việt Nam của `day` đổi sang UTC."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=VN).astimezone(UTC)


def _container_no(index: int) -> str:
    prefix = f"SEDU{index:06d}"
    return prefix + str(container_check_digit(prefix))


def _split(total: int, parts: int) -> list[int]:
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def _weighted(rng: Random, mix: list[tuple[str, int]]) -> str:
    return rng.choices([m[0] for m in mix], weights=[m[1] for m in mix])[0]


def _tracking_code(rng: Random, used: set[str]) -> str:
    while True:
        code = "".join(rng.choice(ALPHABET) for _ in range(10))
        if code not in used:
            used.add(code)
            return code


def _phone(rng: Random) -> str:
    return "09" + "".join(str(rng.randint(0, 9)) for _ in range(8))


class _Builder:
    def __init__(self, seed: int, as_of: date):
        self.rng, self.as_of = Random(seed), as_of  # noqa: S311 - dữ liệu demo, không phải bí mật
        self.codes: set[str] = set()
        self.container_serial = 0

    def containers(self, count: int, discharged_day: date | None, gate_out_at: datetime | None,
                   returned_at: datetime | None) -> tuple[ContainerPlan, ...]:
        made = []
        for k in range(count):
            self.container_serial += 1
            shift = timedelta(minutes=20 * k)
            made.append(ContainerPlan(
                _container_no(self.container_serial), "40HC" if k % 2 == 0 else "20GP",
                vn(discharged_day, 9) + shift if discharged_day else None,
                gate_out_at + shift if gate_out_at else None, returned_at + shift if returned_at else None))
        return tuple(made)

    def timeline(self, scenario: Scenario) -> dict:
        """Mốc thời gian của lô, tính lùi từ as_of theo `age` (ngày kể từ lúc dỡ hàng)."""
        rank = STATUS_ORDER.index(scenario.status) if scenario.status in STATUS_ORDER else 0
        arrival = self.as_of - timedelta(days=scenario.age) if scenario.age is not None else (
            self.as_of - timedelta(days=2) if rank >= 2 else self.as_of + timedelta(days=self.rng.randint(4, 12)))
        return {"rank": rank, "arrival": arrival, "etd": arrival - timedelta(days=14)}

    def orders(self, shipment_at_wh: datetime, status: str, count: int, packages: list[int], drivers: int
               ) -> tuple[OrderPlan, ...]:
        made = []
        for i in range(count):
            forced = FORCED_ORDERS[status]
            order_status = forced[i] if i < len(forced) else _weighted(self.rng, ORDER_MIX[status])
            if status == "DELIVERING" and i == count - 1 and i >= len(forced):
                order_status = "ASSIGNED"  # luôn còn đơn dở để lô chưa tự COMPLETED
            kinds = EVENTS_OF[order_status]
            start = shipment_at_wh + timedelta(hours=2, minutes=3 * i)
            planned = start.astimezone(VN).date() + timedelta(days=1)
            events = tuple((kind, start + timedelta(hours=3 * j)) for j, kind in enumerate(kinds))
            if events and events[-1][1] > vn(self.as_of, 11, 30):  # không có event ở tương lai
                events = tuple((kind, when - timedelta(days=1)) for kind, when in events)
            made.append(OrderPlan(
                _tracking_code(self.rng, self.codes), self.rng.choice(RECIPIENTS), _phone(self.rng),
                f"{self.rng.randint(1, 300)} {self.rng.choice(STREETS)}, {self.rng.choice(DISTRICTS)}, TP.HCM",
                packages[i], min(planned, self.as_of), self.rng.randrange(drivers) if "ASSIGNED" in kinds else None,
                events, order_status))
        return tuple(made)


def _charges(rng: Random, as_of: date, scenario: Scenario, day: date) -> tuple[ChargePlan, ...]:
    if scenario.status in ("CREATED", "IN_TRANSIT", "CANCELLED"):
        return ()
    fx = 25_400
    charges = [ChargePlan("REVENUE", "OCEAN_FREIGHT", rng.randint(8, 40) * 1_000_000, "VND", None, day),
               ChargePlan("COST", "OCEAN_FREIGHT", rng.randint(3, 15) * 100_00, "USD", fx, day)]
    if scenario.status in ("CLEARED", "AT_WAREHOUSE", "DELIVERING", "COMPLETED"):
        charges.append(ChargePlan("COST", "TRUCKING", rng.randint(2, 6) * 500_000, "VND", None, min(day, as_of)))
        charges.append(ChargePlan("REVENUE", "LAST_MILE", rng.randint(2, 9) * 500_000, "VND", None, min(day, as_of)))
    return tuple(charges)


def _trucking(containers: tuple[ContainerPlan, ...], arrival: date, cleared_day: date) -> list[TruckingPlan]:
    """Lệnh lấy hàng đầy (và trả vỏ nếu đã trả) cho từng container đã ra cảng."""
    plans = []
    for i, c in enumerate(containers):
        offset = timedelta(minutes=20 * i)
        done = c.gate_out + timedelta(hours=2)
        plans.append(TruckingPlan(i, "PICKUP_FULL", vn(arrival + timedelta(days=2), 8) + offset, (
            ("ASSIGNED", vn(cleared_day, 15)), ("STARTED", c.gate_out), ("COMPLETED", done))))
        if c.returned:
            plans.append(TruckingPlan(i, "RETURN_EMPTY", vn(arrival + timedelta(days=3), 8) + offset, (
                ("ASSIGNED", vn(arrival + timedelta(days=3), 15)), ("STARTED", c.returned - timedelta(hours=2)),
                ("COMPLETED", c.returned))))
    return plans


def _shipment(builder: _Builder, scenario: Scenario, containers_n: int, orders_n: int, packages: list[int],
              index: int) -> ShipmentPlan:
    rng, as_of = builder.rng, builder.as_of
    t = builder.timeline(scenario)
    arrival, rank, status = t["arrival"], t["rank"], scenario.status
    fcl = scenario.load_type == "FCL"
    discharge_day = arrival if (scenario.age is not None and rank >= 2 and fcl) else None
    transitions = [("CREATED", vn(t["etd"] - timedelta(days=6), 9), False)]
    if status == "CANCELLED":
        transitions.append(("CANCELLED", vn(as_of - timedelta(days=3), 10), False))
    if rank >= 1:
        transitions.append(("IN_TRANSIT", vn(t["etd"], 9), False))
    if rank >= 2:
        transitions.append(("ARRIVED", vn(arrival, 6), False))
    if rank >= 3:
        transitions.append(("CUSTOMS_CLEARING", vn(arrival, 10), False))
    cleared_day = arrival + timedelta(days=1)
    declaration = None
    if rank >= 3:
        cleared = vn(cleared_day, 9) if rank >= 4 else None
        declaration = (f"{306_000_000_000 + index * 7 + 1:012d}", vn(arrival, 10, 30), cleared)
    if rank >= 4:
        transitions.append(("CLEARED", vn(cleared_day, 9, 30), False))
    gate_out = returned = None
    if rank >= 5 and fcl:
        gate_out = vn(arrival + timedelta(days=2), 8, 30)
    if rank >= 7 and fcl:
        returned = vn(arrival + timedelta(days=4), 10)
    containers = builder.containers(containers_n if fcl else 0, discharge_day, gate_out, returned)
    trucking = _trucking(containers, arrival, cleared_day) if gate_out else []
    at_wh = None
    if rank >= 5:
        at_wh = (max(trk.events[-1][1] for trk in trucking if trk.kind == "PICKUP_FULL") if trucking
                 else vn(cleared_day + timedelta(days=1), 10))
        transitions.append(("AT_WAREHOUSE", at_wh, fcl))
    orders: tuple[OrderPlan, ...] = ()
    via = scenario.delivery_mode == "VIA_WAREHOUSE"
    if via and rank >= 5 and orders_n:
        orders = builder.orders(at_wh, status, orders_n, packages, DRIVER_COUNT)
        picked = [o for o in orders if any(k == "PICKED_UP" for k, _ in o.events)]
        if rank >= 6:
            first_pick = min(w for o in picked for k, w in o.events if k == "PICKED_UP")
            transitions.append(("DELIVERING", first_pick, True))
        if rank >= 7:
            last = max([w for o in orders if o.status == "DELIVERED" for _, w in o.events] + [returned or at_wh])
            transitions.append(("COMPLETED", max(last, returned or last), True))
    elif status == "COMPLETED":  # giao tới cửa: xong khi mọi container đã trả rỗng
        transitions.append(("COMPLETED", max(c.returned for c in containers), True))
    active = sum(o.packages for o in orders if o.status not in ("RETURNED", "CANCELLED"))
    delivered = sum(o.packages for o in orders if o.status == "DELIVERED")
    total = delivered if (status == "COMPLETED" and orders) else active + (rng.randint(5, 40) if orders else
                                                                            rng.randint(20, 400))
    docs = tuple(doc for need, doc in DOC_RULES if rank >= STATUS_ORDER.index(need)) if status != "CANCELLED" else ()
    if fcl and rank >= 1 and status != "CANCELLED":
        docs += ("MBL",)
    if scenario.fta and rank >= 3:
        docs += ("ORIGIN_PROOF",)
    pods = ["VNSGN", "VNHPH", "VNCMT"]
    do_until = as_of + timedelta(days=1) if scenario.do_expiring else (
        arrival + timedelta(days=rng.randint(5, 12)) if rank >= 4 else None)
    day = min(as_of, arrival + timedelta(days=3))
    return ShipmentPlan(scenario, scenario.carrier, rng.choice(["CNSHA", "CNNGB", "KRPUS", "SGSIN"]),
                        pods[index % 3], t["etd"], arrival, total, do_until, tuple(transitions), containers,
                        declaration, docs, tuple(trucking), orders, _charges(rng, as_of, scenario, day))


def build_dataset(seed: int, size: str, as_of: date) -> Dataset:
    target = SIZES[size]
    builder = _Builder(seed, as_of)
    scenarios = [SCENARIOS[i % len(SCENARIOS)] for i in range(target["shipments"])]
    fcl_slots = [i for i, s in enumerate(scenarios) if s.load_type == "FCL"]
    container_counts = dict(zip(fcl_slots, _split(target["containers"], len(fcl_slots)), strict=True))
    order_slots = [i for i, s in enumerate(scenarios) if s.delivery_mode == "VIA_WAREHOUSE"
                   and s.status in ORDER_MIX]
    order_counts = dict(zip(order_slots, _split(target["orders"], len(order_slots)), strict=True))
    shipments = []
    for i, scenario in enumerate(scenarios):
        n = order_counts.get(i, 0)
        packages = [builder.rng.randint(1, 12) for _ in range(n)]
        shipments.append(_shipment(builder, scenario, container_counts.get(i, 0), n, packages, i))
    return Dataset(seed, size, as_of, tuple(shipments))
