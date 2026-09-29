"""Danh mục HS nhỏ dựng tay và vector đơn vị để test tìm kiếm / gợi ý không cần model thật."""

import math

from app.ai.hs.suggest import HsPick, PickItem

ROWS = [  # (code, mô tả VI, mô tả EN, trục vector)
    ("84713020", "Máy xử lý dữ liệu tự động loại xách tay > Máy tính xách tay", "Portable automatic data processing machines > Laptops", 0),
    ("84713010", "Máy xử lý dữ liệu tự động loại xách tay > Máy tính bảng", "Portable machines > Tablets", 1),
    ("85171300", "Điện thoại thông minh", "Smartphones", 2),
    ("61091010", "Áo phông, áo may ô, bằng bông", "T-shirts, singlets, of cotton", 3),
    ("10063090", "Gạo đã xát toàn bộ hoặc sơ bộ", "Semi-milled or wholly milled rice", 4),
    ("01012100", "Ngựa thuần chủng để nhân giống", "Pure-bred breeding horses", 5),
    ("73065090", "Ống bằng thép không gỉ", "Stainless steel tubes", 6),
    ("39012000", "Polyetylen có trọng lượng riêng từ 0,94 trở lên", "Polyethylene", 7),
]


def unit(axis: int, mix: dict[int, float] | None = None) -> list[float]:
    vector = [0.0] * 1024
    vector[axis] = 1.0
    for other, weight in (mix or {}).items():
        vector[other] = weight
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector]


LAPTOP = "84713020"
USAGE = {"input_tokens": 900, "output_tokens": 100, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


def pick(*codes: str, insufficient: bool = False) -> HsPick:
    return HsPick(insufficient=insufficient, picks=[PickItem(code=c, explanation=f"Vì {c} khớp mô tả") for c in codes])
