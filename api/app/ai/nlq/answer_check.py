"""Kiểm câu trả lời của LLM với bảng kết quả: mọi số trong câu trả lời phải có trong bảng, biểu đồ đúng cột."""

import re
from typing import Any

TOLERANCE = 0.01
CHART_TYPES = ("bar", "line", "pie")

# Thứ tự ưu tiên: ngày dd/mm/yyyy hoặc mm/yyyy, ngày ISO (yyyy-mm[-dd]), số có phân cách nghìn / thập phân
_TOKEN = re.compile(
    r"(?<![\w.,/-])(?:(?P<vn_date>\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4})"
    r"|(?P<iso>\d{4}-\d{2}(?:-\d{2})?)"
    r"|(?P<num>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?))(?P<pct>%)?(?![\w/-])")


def _number_values(token: str) -> set[float]:
    """Các cách đọc có thể của một số: `1.234.567` (nghìn kiểu VN), `1,5` (thập phân VN), `1,234` (nghìn kiểu Anh)."""
    values: set[float] = set()
    candidates = {token.replace(".", "").replace(",", ""),  # mọi dấu là phân cách nghìn
                  token.replace(".", "").replace(",", "."),  # `.` nghìn, `,` thập phân (VN)
                  token.replace(",", "")}  # `,` nghìn, `.` thập phân (Anh)
    for candidate in candidates:
        try:
            values.add(float(candidate))
        except ValueError:
            continue
    return values


def _iso_from_vn_date(token: str) -> str:
    parts = token.split("/")
    return f"{parts[-1]}-{int(parts[-2]):02d}" + (f"-{int(parts[0]):02d}" if len(parts) == 3 else "")


def _cells(rows: list[list[Any]]) -> tuple[list[float], list[str]]:
    numbers = [float(c) for row in rows for c in row if isinstance(c, int | float) and not isinstance(c, bool)]
    texts = [str(c) for row in rows for c in row if isinstance(c, str)]
    return numbers, texts


def numbers_supported(answer: str, rows: list[list[Any]]) -> bool:
    """Mỗi số trong câu trả lời bằng một ô số (lệch ≤ 0,01), hoặc là chuỗi con của ô text / ngày, hoặc bằng số dòng."""
    numbers, texts = _cells(rows)
    for match in _TOKEN.finditer(answer):
        token = match.group("vn_date") or match.group("iso") or match.group("num")
        if match.group("num"):
            values = _number_values(token)
            if match.group("pct"):
                values |= {v / 100 for v in values}
            if any(abs(v - n) <= TOLERANCE for v in values for n in [*numbers, float(len(rows))]):
                continue
            if any(token in text for text in texts):
                continue
            return False
        iso = _iso_from_vn_date(token) if match.group("vn_date") else token
        if not any(iso in text for text in texts):
            return False
    return True


def valid_chart(chart: dict | None, columns: list[str], rows: list[list[Any]]) -> dict | None:
    """Biểu đồ chỉ giữ khi `x`, `y` là cột có trong kết quả và `y` toàn số; sai thì bỏ (None)."""
    if not chart or chart.get("type") not in CHART_TYPES:
        return None
    x, y = chart.get("x"), chart.get("y")
    if x not in columns or y not in columns:
        return None
    y_index = columns.index(y)
    values = [row[y_index] for row in rows if row[y_index] is not None]
    if not values or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in values):
        return None
    return {"type": chart["type"], "x": x, "y": y}
