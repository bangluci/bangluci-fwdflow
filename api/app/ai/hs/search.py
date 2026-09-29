"""Tìm ứng viên mã HS: nhánh K (full-text, khớp bất kỳ từ nào), nhánh V (vector bge-m3), trộn bằng RRF."""

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.hs import embed

BRANCH_LIMIT = 50
RRF_K = 60
HNSW_EF_SEARCH = 100
Mode = Literal["K", "V", "H"]

# `plainto_tsquery` nối các từ bằng `&`; đổi thành `|` để một dòng invoice dài có từ lạ vẫn ra ứng viên.
_FULLTEXT = text("""
WITH q AS (
    SELECT replace(plainto_tsquery('vn_simple', :q)::text, '&', '|')::tsquery AS vi,
           replace(plainto_tsquery('english', :q)::text, '&', '|')::tsquery AS en
)
SELECT h.code, h.description_vi, h.description_en
FROM hs_codes h, q
WHERE h.tsv_vi @@ q.vi OR h.tsv_en @@ q.en
ORDER BY greatest(ts_rank_cd(h.tsv_vi, q.vi), ts_rank_cd(h.tsv_en, q.en)) DESC, h.code
LIMIT :limit
""")
_VECTOR = text("""
SELECT code, description_vi, description_en, 1 - (embedding <=> CAST(:vec AS vector)) AS cosine
FROM hs_codes
ORDER BY embedding <=> CAST(:vec AS vector)
LIMIT :limit
""")
_COSINE_OF = text("""
SELECT code, 1 - (embedding <=> CAST(:vec AS vector)) AS cosine
FROM hs_codes WHERE code = ANY(:codes) AND embedding IS NOT NULL
""")


@dataclass(frozen=True)
class Candidate:
    code: str
    description_vi: str
    description_en: str | None
    rank: int
    k_rank: int | None = None
    v_rank: int | None = None
    rrf_score: float = 0.0
    cosine: float | None = None


@dataclass(frozen=True)
class SearchResult:
    candidates: list[Candidate] = field(default_factory=list)
    degraded: bool = False
    top1_cosine: float | None = None


def rrf_merge(lists: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: điểm của mã = tổng 1/(k + hạng) qua các danh sách (hạng tính từ 1), giảm dần."""
    scores: dict[str, float] = {}
    for ranked in lists:
        for position, code in enumerate(ranked, start=1):
            scores[code] = scores.get(code, 0.0) + 1.0 / (k + position)
    return sorted(scores.items(), key=lambda pair: -pair[1])  # sort ổn định: hoà điểm giữ thứ tự xuất hiện


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _fulltext(db: Session, description: str) -> list[dict]:
    return [dict(row._mapping) for row in db.execute(_FULLTEXT, {"q": description, "limit": BRANCH_LIMIT})]


def _vector(db: Session, vector: list[float]) -> list[dict]:
    db.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
    rows = db.execute(_VECTOR, {"vec": _vector_literal(vector), "limit": BRANCH_LIMIT})
    return [dict(row._mapping) for row in rows if row.cosine is not None]


def _build(order: list[tuple[str, float]], info: dict[str, dict], k_rank: dict[str, int], v_rank: dict[str, int],
           cosines: dict[str, float], limit: int) -> list[Candidate]:
    return [Candidate(code=code, description_vi=info[code]["description_vi"],
                      description_en=info[code]["description_en"], rank=position, k_rank=k_rank.get(code),
                      v_rank=v_rank.get(code), rrf_score=score, cosine=cosines.get(code))
            for position, (code, score) in enumerate(order[:limit], start=1)]


def search_candidates(db: Session, description: str, mode: Mode = "H", limit: int = 20) -> SearchResult:
    """`K` / `V` / `H` trả top-`limit` của nhánh K, nhánh V, hoặc RRF(K, V). Model chưa nạp → chỉ K và `degraded`."""
    vector = None if mode == "K" else embed.embed_query(description)
    degraded = mode != "K" and vector is None
    keyword = _fulltext(db, description) if mode in ("K", "H") or degraded else []
    semantic = _vector(db, vector) if vector is not None else []

    info = {row["code"]: row for row in [*keyword, *semantic]}
    k_rank = {row["code"]: i for i, row in enumerate(keyword, start=1)}
    v_rank = {row["code"]: i for i, row in enumerate(semantic, start=1)}
    cosines = {row["code"]: float(row["cosine"]) for row in semantic}
    top1_cosine = float(semantic[0]["cosine"]) if semantic else None

    if mode == "K" or degraded:
        order = [(row["code"], 1.0 / (RRF_K + i)) for i, row in enumerate(keyword, start=1)]
    elif mode == "V":
        order = [(row["code"], 1.0 / (RRF_K + i)) for i, row in enumerate(semantic, start=1)]
    else:
        order = rrf_merge([[r["code"] for r in keyword], [r["code"] for r in semantic]])

    top = order[:limit]
    missing = [code for code, _ in top if code not in cosines]
    if vector is not None and missing:
        rows = db.execute(_COSINE_OF, {"vec": _vector_literal(vector), "codes": missing})
        cosines.update({row.code: float(row.cosine) for row in rows})
    return SearchResult(_build(order, info, k_rank, v_rank, cosines, limit), degraded, top1_cosine)
