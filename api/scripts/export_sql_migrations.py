"""Xuất các migration Alembic thành file SQL thuần để đọc: `migrations/sql/NNNN_ten.up.sql` và `.down.sql`.

Alembic vẫn là công cụ chạy migration. File .sql sinh tự động từ `migrations/versions/*.py`, không sửa tay;
mật khẩu role `nlq_*` được thay bằng chỗ giữ chỗ. Chạy: python -m scripts.export_sql_migrations.
"""

import importlib.util
import sys
import textwrap
from pathlib import Path
from types import ModuleType

from app.config import get_settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = API_ROOT / "migrations" / "versions"
SQL_DIR = API_ROOT / "migrations" / "sql"
PLACEHOLDERS = {"nlq_ops_password": "<NLQ_OPS_PASSWORD>", "nlq_finance_password": "<NLQ_FINANCE_PASSWORD>"}
DIRECTIONS = (("up", "upgrade"), ("down", "downgrade"))
HEADER = ("-- Sinh tự động từ migrations/versions/{source} ({direction}). KHÔNG sửa tay, KHÔNG chạy trực tiếp:\n"
          "-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations\n\n")


class _Recorder:
    """Thế chỗ `alembic.op` lúc xuất: gom các chuỗi SQL mà migration sẽ chạy thay vì gửi xuống DB."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str) -> None:
        self.statements.append(textwrap.dedent(str(sql)).strip().rstrip(";").rstrip() + ";")

    def __getattr__(self, name: str):
        raise NotImplementedError(f"Migration gọi op.{name}: bộ xuất SQL chỉ hỗ trợ op.execute")


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"sql_export_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(path: Path, direction: str) -> str:
    module, recorder = _load(path), _Recorder()
    module.op = recorder
    if hasattr(module, "get_settings"):  # 0012 đọc mật khẩu role từ cấu hình: không để lọt vào file
        masked = get_settings().model_copy(update=PLACEHOLDERS)
        module.get_settings = lambda: masked
    getattr(module, direction)()
    return HEADER.format(source=path.name, direction=direction) + "\n\n".join(recorder.statements) + "\n"


def render_all() -> dict[str, str]:
    """Tên file → nội dung SQL của từng migration, theo thứ tự revision."""
    return {f"{path.stem}.{suffix}.sql": _render(path, direction)
            for path in sorted(VERSIONS_DIR.glob("[0-9]*.py")) for suffix, direction in DIRECTIONS}


def write_all() -> list[str]:
    files = render_all()
    SQL_DIR.mkdir(exist_ok=True)
    for stale in {p.name for p in SQL_DIR.glob("*.sql")} - set(files):
        (SQL_DIR / stale).unlink()
    for name, content in files.items():
        (SQL_DIR / name).write_text(content, encoding="utf-8", newline="\n")
    return sorted(files)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # in tiếng Việt được cả khi Windows pipe ra file
    names = write_all()
    print(f"Đã ghi {len(names)} file vào {SQL_DIR.relative_to(API_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
