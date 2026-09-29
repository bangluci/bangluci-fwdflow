"""Kiểm tra cấu hình bậc phí và bộ loại phí của một phiên bản quy tắc free time."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.envelope import AppError

CURRENCIES = frozenset({"VND", "USD"})


@dataclass(frozen=True)
class TierIn:
    from_day: int
    to_day: int | None
    rate_amount: int
    currency: str


class TierConfigError(AppError):
    def __init__(self, code: str, reason: str, message: str, index: int | None = None) -> None:
        super().__init__(code, message, 400, {"reason": reason, "index": index})


def _bad(reason: str, message: str, index: int | None = None) -> TierConfigError:
    return TierConfigError("INVALID_TIERS", reason, message, index)


def _check_values(ordered: Sequence[TierIn]) -> None:
    for index, tier in enumerate(ordered):
        if tier.from_day < 1 or (tier.to_day is not None and tier.to_day < tier.from_day) or tier.rate_amount < 0 \
                or tier.currency not in CURRENCIES:
            raise _bad("BAD_VALUE", "Bậc phí có giá trị không hợp lệ (ngày ≥ 1, đến ≥ từ, đơn giá ≥ 0, VND hoặc USD)",
                       index)


def _check_links(free_days: int, ordered: Sequence[TierIn]) -> None:
    if ordered[0].from_day != free_days + 1:
        raise _bad("FIRST_TIER_START", f"Bậc đầu phải bắt đầu ở ngày {free_days + 1} (ngày free + 1)", 0)
    for index in range(1, len(ordered)):
        previous, tier = ordered[index - 1], ordered[index]
        if previous.to_day is None:
            raise _bad("OPEN_TIER_NOT_LAST", "Chỉ bậc cuối được để trống ngày kết thúc", index - 1)
        if tier.from_day <= previous.to_day:
            raise _bad("OVERLAP", "Hai bậc phí chồng lên nhau", index)
        if tier.from_day > previous.to_day + 1:
            raise _bad("GAP", "Giữa hai bậc phí có khoảng trống ngày", index)
    if ordered[-1].to_day is not None:
        raise _bad("LAST_TIER_CLOSED", "Bậc cuối phải để trống ngày kết thúc (tính từ đó trở đi)", len(ordered) - 1)


def validate_tiers(free_days: int, tiers: Sequence[TierIn]) -> None:
    """Bậc đầu bắt đầu ở free + 1, các bậc liền nhau không chồng, bậc cuối mở, một loại tiền tệ."""
    if not tiers:
        raise _bad("EMPTY", "Quy tắc cần ít nhất một bậc phí")
    ordered = sorted(tiers, key=lambda t: t.from_day)
    _check_values(ordered)
    _check_links(free_days, ordered)
    if len({t.currency for t in ordered}) > 1:
        raise _bad("MIXED_CURRENCY", "Các bậc của một quy tắc phải cùng một loại tiền tệ")


def validate_fee_type_set(fee_types: Iterable[str]) -> None:
    """Một phiên bản quy tắc chỉ dùng `COMBINED` hoặc cặp `DEM` + `DET`, mỗi loại một lần."""
    values = list(fee_types)

    def bad(reason: str, message: str) -> TierConfigError:
        return TierConfigError("INVALID_RULE_SET", reason, message)

    if not values:
        raise bad("EMPTY", "Cần ít nhất một loại phí")
    if len(values) != len(set(values)):
        raise bad("DUPLICATE_FEE_TYPE", "Mỗi loại phí chỉ được khai một lần")
    kinds = set(values)
    if "COMBINED" in kinds and kinds != {"COMBINED"}:
        raise bad("MIXED_COMBINED", "COMBINED không dùng chung với DEM / DET trong cùng ngày hiệu lực")
    if "COMBINED" not in kinds and kinds != {"DEM", "DET"}:
        raise bad("INCOMPLETE_PAIR", "Phải khai đủ cả DEM và DET")
