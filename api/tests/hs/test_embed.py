from app.ai.hs import embed
from app.config import get_settings


def test_embed_query_returns_none_before_load():
    embed.reset()
    assert embed.model_ready() is False
    assert embed.embed_query("máy tính xách tay") is None


def test_load_failure_sets_error_and_model_not_ready(tmp_path, monkeypatch):
    embed.reset()
    monkeypatch.setattr(get_settings(), "embed_model_dir", tmp_path / "missing")
    embed.start_background_load().join(timeout=30)
    assert embed.model_ready() is False
    assert embed.load_error() is not None
    assert embed.embed_query("x") is None
    embed.reset()
