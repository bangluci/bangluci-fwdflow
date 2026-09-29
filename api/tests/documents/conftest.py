import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    """Mọi test chứng từ ghi file vào thư mục tạm, không đụng data/files của repo."""
    target = tmp_path / "files"
    monkeypatch.setattr(get_settings(), "files_dir", target)
    return target
