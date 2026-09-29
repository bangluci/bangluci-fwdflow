"""Embedding bge-m3 chạy cục bộ trên CPU. Model nạp ở luồng nền để API khởi động không phải chờ; chưa nạp xong thì
`embed_query` trả None và tìm kiếm rút gọn còn full-text."""

import argparse
import logging
import os
import statistics
import sys
import threading
import time
from typing import Any

from sqlalchemy import select, text

from app.config import get_settings

log = logging.getLogger("fwdflow.hs")

BATCH_QUERY = 32
BATCH_DB = 64
BENCH_SAMPLES = (
    "Máy tính xách tay 14 inch, CPU Intel, RAM 16GB", "Điện thoại di động thông minh", "Áo thun cotton nam cổ tròn",
    "Ống thép không gỉ đường kính 25mm", "Hạt nhựa polyethylene dạng nguyên sinh", "Linh kiện điện tử bản mạch in",
    "Gạo thơm đóng túi 5kg", "Giày thể thao đế cao su", "Bột giặt đóng gói", "Động cơ điện xoay chiều 3 pha",
)

_lock = threading.Lock()
_model: Any = None
_load_error: str | None = None
_thread: threading.Thread | None = None


def _load() -> Any:
    """Nạp model đồng bộ; chỉ đọc từ thư mục cục bộ (không tải mạng)."""
    global _model, _load_error
    with _lock:
        if _model is not None:
            return _model
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"  # đặt trước khi import để không kết nối Hugging Face
            from sentence_transformers import SentenceTransformer

            started = time.perf_counter()
            _model = SentenceTransformer(str(get_settings().embed_model_dir), device="cpu")
            _load_error = None
            log.info("Đã nạp bge-m3 sau %.1fs", time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001 - mọi lỗi nạp đều chỉ làm tìm kiếm rút gọn, không sập API
            _load_error = f"{type(exc).__name__}: {exc}"
            log.error("Không nạp được bge-m3: %s", _load_error)
        return _model


def start_background_load() -> threading.Thread:
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_load, name="embed-load", daemon=True)
        _thread.start()
    return _thread


def model_ready() -> bool:
    return _model is not None


def load_error() -> str | None:
    return _load_error


def reset() -> None:
    """Chỉ cho test: quên model đã nạp."""
    global _model, _load_error, _thread
    _model, _load_error, _thread = None, None, None


def embed_query(query: str) -> list[float] | None:
    """None khi model chưa nạp xong hoặc nạp lỗi; không bao giờ đứng chờ."""
    if _model is None:
        return None
    return _model.encode([query], normalize_embeddings=True, batch_size=BATCH_QUERY)[0].tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Nạp model đồng bộ nếu cần (dùng cho CLI và eval)."""
    model = _load()
    if model is None:
        raise RuntimeError(f"Không nạp được model embedding: {_load_error}")
    return [vec.tolist() for vec in model.encode(texts, normalize_embeddings=True, batch_size=BATCH_QUERY)]


def _stats(db) -> tuple[int, int]:
    total, embedded = db.execute(text("SELECT count(*), count(embedding) FROM hs_codes")).one()
    return int(total), int(embedded)


def embed_catalog(db) -> tuple[int, int]:
    """Embed các dòng `embedding IS NULL` theo nhóm 64, commit từng nhóm nên chạy lại là làm tiếp."""
    from app.ai.hs.models import HsCode

    done = 0
    while True:
        rows = db.scalars(select(HsCode).where(HsCode.embedding.is_(None)).order_by(HsCode.code).limit(BATCH_DB)).all()
        if not rows:
            break
        vectors = embed_texts([f"{r.description_vi}\n{r.description_en}" if r.description_en else r.description_vi
                               for r in rows])
        for row, vector in zip(rows, vectors, strict=True):
            row.embedding = vector
        db.commit()
        done += len(rows)
        print(f"embedded={done}", file=sys.stderr, flush=True)
    total, embedded = _stats(db)
    return done, total - embedded


def bench(count: int) -> tuple[float, float]:
    samples = [BENCH_SAMPLES[i % len(BENCH_SAMPLES)] for i in range(count)]
    _load()
    if _model is None:
        raise RuntimeError(f"Không nạp được model embedding: {_load_error}")
    timings = []
    for sample in samples:
        started = time.perf_counter()
        _model.encode([sample], normalize_embeddings=True)
        timings.append((time.perf_counter() - started) * 1000)
    ordered = sorted(timings)
    return statistics.median(ordered), ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embed danh mục HS bằng bge-m3")
    parser.add_argument("--stats", action="store_true", help="in số dòng đã embed")
    parser.add_argument("--bench", type=int, metavar="N", help="đo độ trễ embed N câu")
    args = parser.parse_args(argv)
    if args.bench:
        p50, p95 = bench(args.bench)
        print(f"p50_ms={p50:.0f} p95_ms={p95:.0f}")
        return 0
    from app.db import SessionLocal

    with SessionLocal() as db:
        if args.stats:
            total, embedded = _stats(db)
            print(f"total={total} embedded={embedded}")
            return 0
        done, remaining = embed_catalog(db)
    print(f"embedded={done} remaining={remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
