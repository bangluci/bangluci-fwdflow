import pytest
from sqlalchemy import text

from app.ai.hs import embed, search
from app.ai.hs.models import HsCode
from app.ai.hs.search import rrf_merge, search_candidates
from tests.hs.catalog import unit


def test_rrf_merge_matches_manual():
    merged = rrf_merge([["A", "B", "C"], ["C", "B"]])
    assert [code for code, _ in merged] == ["C", "B", "A"]
    assert [round(score, 6) for _, score in merged] == [0.032266, 0.032258, 0.016393]


def test_fulltext_matches_unaccented_vietnamese(db, catalog):
    result = search_candidates(db, "may tinh xach tay", mode="K")
    assert "84713020" in [c.code for c in result.candidates]
    assert result.degraded is False and result.top1_cosine is None


def test_fulltext_or_semantics_for_long_invoice_line(db, catalog):
    result = search_candidates(db, "Máy tính xách tay hiệu Dell XPS 9310 màu bạc lô số 77", mode="K")
    assert result.candidates[0].code in ("84713020", "84713010")
    assert "84713020" in [c.code for c in result.candidates]


def test_fulltext_english_config_stems(db, catalog):
    result = search_candidates(db, "laptops", mode="K")
    assert [c.code for c in result.candidates] == ["84713020"]


def test_hybrid_returns_at_most_20_with_ranks_and_cosine(db, catalog, query_vector):
    for i in range(30):
        db.add(HsCode(code=f"9{i:07d}"[:8].replace("9", "8", 1), chapter=84, description_vi=f"Máy xách tay loại {i}",
                      embedding=unit(100 + i)))
    db.flush()
    result = search_candidates(db, "máy tính xách tay")
    codes = [c.code for c in result.candidates]
    assert len(codes) == 20 and len(set(codes)) == 20
    assert [c.rank for c in result.candidates] == list(range(1, 21))
    assert codes[0] == "84713020"
    assert result.candidates[0].cosine == pytest.approx(0.9285, abs=1e-3)
    assert result.candidates[0].k_rank is not None and result.candidates[0].v_rank == 1
    assert result.top1_cosine == pytest.approx(result.candidates[0].cosine)
    assert all(c.cosine is not None for c in result.candidates)  # kể cả mã chỉ có ở nhánh K


def test_search_degrades_to_fulltext_when_model_missing(db, catalog, monkeypatch):
    monkeypatch.setattr(embed, "embed_query", lambda _text: None)
    result = search_candidates(db, "máy tính xách tay")
    assert result.degraded is True and result.top1_cosine is None
    assert result.candidates and result.candidates[0].code == "84713020"
    assert all(c.v_rank is None and c.cosine is None for c in result.candidates)


def test_vector_query_uses_hnsw_index(db, catalog):
    db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(row[0] for row in db.execute(text("EXPLAIN " + str(search._VECTOR)),
                                                   {"vec": search._vector_literal(unit(0)), "limit": 5}))
    assert "ix_hs_codes_embedding_hnsw" in plan
