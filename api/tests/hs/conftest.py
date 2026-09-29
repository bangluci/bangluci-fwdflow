import pytest

from app.ai.claude import StructuredResult
from app.ai.hs import embed, suggest
from app.ai.hs.models import HsCode
from tests.hs.catalog import ROWS, USAGE, unit


@pytest.fixture
def catalog(db):
    for code, vi, en, axis in ROWS:
        db.add(HsCode(code=code, chapter=int(code[:2]), description_vi=vi, description_en=en, embedding=unit(axis)))
    db.flush()


@pytest.fixture
def query_vector(monkeypatch):
    """`query_vector(v)` cố định vector `embed_query`; mặc định gần mã máy tính xách tay (cosine ≈ 0.93)."""

    def install(vector):
        monkeypatch.setattr(embed, "embed_query", lambda _text: vector)

    install(unit(0, {1: 0.4}))
    return install


@pytest.fixture
def claude(monkeypatch):
    """`claude(kết quả | lỗi)`: thay `call_structured`; trả danh sách các lần gọi (system, khối nội dung)."""
    calls: list[tuple] = []

    def install(outcome):
        def fake(feature, system, blocks, schema, max_tokens):
            calls.append((system, blocks))
            if isinstance(outcome, Exception):
                raise outcome
            return StructuredResult(outcome, "{}", "end_turn", 12, USAGE, {"model": "claude-test"})

        monkeypatch.setattr(suggest, "call_structured", fake)
        return calls

    return install
