import hashlib
import io
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.documents.storage import path_for, save_upload
from app.envelope import AppError
from tests.documents import pdf_factory as factory


def _upload(data: bytes):
    return SimpleNamespace(file=io.BytesIO(data))


def test_save_upload_pdf_sha256_matches_input(files_dir):
    data = factory.simple_pdf(2)
    stored = save_upload(_upload(data))
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert (stored.mime, stored.pages, stored.size) == ("application/pdf", 2, len(data))
    assert path_for(stored.sha256).read_bytes() == data


def test_save_upload_same_content_one_file(files_dir):
    data = factory.simple_pdf()
    first, second = save_upload(_upload(data)), save_upload(_upload(data))
    assert first.sha256 == second.sha256
    assert [p.name for p in files_dir.iterdir() if p.name != "tmp"] == [first.sha256]


def test_save_upload_over_limit_rejected_and_temp_removed(files_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1000)
    with pytest.raises(AppError) as err:
        save_upload(_upload(b"%PDF-" + b"0" * 2000))
    assert err.value.code == "FILE_TOO_LARGE"
    assert list((files_dir / "tmp").iterdir()) == []


def test_save_upload_unknown_type_400(files_dir):
    with pytest.raises(AppError) as err:
        save_upload(_upload(b"MZ\x90\x00 exe"))
    assert err.value.code == "UNSUPPORTED_FILE_TYPE" and list((files_dir / "tmp").iterdir()) == []


def test_save_upload_png_stored_as_jpeg(files_dir):
    stored = save_upload(_upload(factory.png_bytes((30, 20))))
    assert (stored.mime, stored.pages) == ("image/jpeg", 1)
    assert path_for(stored.sha256).read_bytes().startswith(b"\xff\xd8\xff")


def test_path_for_rejects_non_hex():
    with pytest.raises(ValueError, match="SHA-256"):
        path_for("../../etc/passwd")
