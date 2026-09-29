import sys
import types

from app.ai.hs import embed
from app.config import get_settings


def test_embed_query_returns_none_before_load():
    embed.reset()
    assert embed.model_ready() is False
    assert embed.embed_query("máy tính xách tay") is None


def test_load_failure_sets_error_and_model_not_ready(tmp_path, monkeypatch):
    """Thư mục model không có: nạp lỗi, `model_ready()` là False, `embed_query` vẫn trả None và không ném lỗi.
    Dùng thư viện giả để test không phụ thuộc việc torch có cài hay không và không mất thời gian import."""
    embed.reset()
    missing = tmp_path / "missing"
    fake = types.ModuleType("sentence_transformers")

    class SentenceTransformer:
        def __init__(self, path, device):
            raise OSError(f"không thấy model ở {path}")

    fake.SentenceTransformer = SentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    monkeypatch.setattr(get_settings(), "embed_model_dir", missing)
    embed.start_background_load().join(timeout=30)
    assert embed.model_ready() is False
    assert "missing" in embed.load_error()
    assert embed.embed_query("x") is None
    embed.reset()
