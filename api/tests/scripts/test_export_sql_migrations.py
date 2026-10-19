from app.config import get_settings
from scripts.export_sql_migrations import PLACEHOLDERS, SQL_DIR, render_all


def test_sql_files_match_migrations():
    on_disk = {path.name: path.read_text(encoding="utf-8") for path in SQL_DIR.glob("*.sql")}
    assert on_disk == render_all(), "migrations/sql lệch migrations/versions: chạy python -m scripts.export_sql_migrations"


def test_export_masks_role_passwords():
    settings = get_settings()
    secrets = [value for value in (settings.nlq_ops_password, settings.nlq_finance_password) if value]
    exported = "".join(render_all().values())
    assert all(placeholder in exported for placeholder in PLACEHOLDERS.values())
    assert not any(secret in exported for secret in secrets)
