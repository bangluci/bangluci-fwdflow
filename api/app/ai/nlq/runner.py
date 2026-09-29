"""Chạy SQL đã kiểm bằng kết nối riêng của role chỉ đọc (nlq_ops / nlq_finance): read-only, có trần thời gian,
luôn rollback. Đây là lớp phòng thủ thứ hai: dù validator sót, role không có quyền ghi và không đọc được bảng gốc."""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import psycopg
from sqlalchemy.engine import URL, make_url

from app.config import get_settings

MAX_ROWS = 500
STATEMENT_TIMEOUT = "5s"
LOCK_TIMEOUT = "1s"
CONNECT_TIMEOUT_SECONDS = 5


class NlqTimeout(Exception):
    """Truy vấn quá thời gian cho phép (5 giây) hoặc chờ khoá quá lâu."""


class NlqExecError(Exception):
    """Postgres từ chối hoặc lỗi khi chạy; `str(exc)` là thông điệp chính của Postgres (chỉ để sửa SQL / ghi log)."""


@dataclass(frozen=True)
class RunResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


def _password(role: str) -> str:
    settings = get_settings()
    passwords = {"nlq_ops": settings.nlq_ops_password, "nlq_finance": settings.nlq_finance_password}
    if role not in passwords:
        raise ValueError(f"role không hợp lệ: {role}")
    return passwords[role]


def _json_safe(value: Any) -> Any:
    """Giá trị của ô kết quả → kiểu JSON: số thập phân nguyên thành int, ngày giờ thành chuỗi ISO."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value


def run_readonly(sql: str, nlq_role: str, as_of: date | str, url: URL | str | None = None) -> RunResult:
    """`url` mặc định là `DATABASE_URL`; service truyền URL của phiên đang dùng để test chạy đúng DB test."""
    target = make_url(url or get_settings().database_url)
    try:
        connection = psycopg.connect(
            host=target.host, port=target.port, dbname=target.database, user=nlq_role, password=_password(nlq_role),
            connect_timeout=CONNECT_TIMEOUT_SECONDS)
    except psycopg.Error as exc:
        raise NlqExecError(f"không kết nối được role {nlq_role}: {exc}") from exc
    try:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
            cursor.execute("SELECT set_config('app.as_of', %s, true)", (str(as_of),))
            cursor.execute(sql)  # không truyền tham số nên dấu % trong LIKE không bị hiểu là placeholder
            if cursor.description is None:
                raise NlqExecError("câu lệnh không trả về bảng kết quả")
            columns = [column.name for column in cursor.description]
            fetched = cursor.fetchmany(MAX_ROWS + 1)  # dòng thứ 501 chỉ để phát hiện bị cắt
    except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable) as exc:
        raise NlqTimeout(str(exc)) from exc
    except psycopg.Error as exc:
        message = exc.diag.message_primary if getattr(exc, "diag", None) and exc.diag.message_primary else str(exc)
        raise NlqExecError(message) from exc
    finally:
        connection.rollback()
        connection.close()
    truncated = len(fetched) > MAX_ROWS
    rows = [[_json_safe(cell) for cell in row] for row in fetched[:MAX_ROWS]]
    return RunResult(columns, rows, truncated)
