"""Lưu file upload theo nội dung: /data/files/{sha256}. Ghi file tạm → SHA-256 → rename; DB commit sau cùng."""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import uuid4

from app.config import get_settings
from app.documents.sanitize import check_pdf, clean_image, sniff_mime
from app.envelope import AppError

CHUNK_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")


class Upload(Protocol):
    file: BinaryIO


@dataclass(frozen=True)
class StoredFile:
    sha256: str
    mime: str
    size: int
    pages: int


def path_for(sha256: str) -> Path:
    if not _SHA256.fullmatch(sha256):
        raise ValueError("SHA-256 không hợp lệ")
    return get_settings().files_dir / sha256


def _stream_to(src: BinaryIO, dst: Path, limit: int) -> None:
    written = 0
    with dst.open("wb") as out:
        while chunk := src.read(CHUNK_BYTES):
            written += len(chunk)
            if written > limit:
                raise AppError("FILE_TOO_LARGE", f"File quá {limit // (1024 * 1024)}MB", 400)
            out.write(chunk)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def save_upload(upload: Upload) -> StoredFile:
    settings = get_settings()
    tmp_dir = settings.files_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    raw, cleaned = tmp_dir / f"{uuid4().hex}.upload", tmp_dir / f"{uuid4().hex}.clean"
    try:
        _stream_to(upload.file, raw, settings.max_upload_bytes)
        with raw.open("rb") as handle:
            mime = sniff_mime(handle.read(16))
        if mime is None:
            raise AppError("UNSUPPORTED_FILE_TYPE", "Chỉ nhận PDF, JPEG, PNG", 400)
        if mime == "application/pdf":
            pages, final = check_pdf(raw), raw
        else:
            clean_image(raw, cleaned)
            mime, pages, final = "image/jpeg", 1, cleaned
        digest = _sha256_of(final)
        dest = path_for(digest)
        os.replace(final, dest)
        return StoredFile(digest, mime, dest.stat().st_size, pages)
    finally:
        raw.unlink(missing_ok=True)
        cleaned.unlink(missing_ok=True)
