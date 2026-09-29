from openpyxl import Workbook
from sqlalchemy import text

from app.ai.hs.importer import COLUMNS, FIRST_DATA_ROW, import_hs, parse_rows
from app.ai.hs.models import HsCode

HORSES = [
    ("0101", "Ngựa, lừa, la sống.", "Live horses, asses, mules"),
    (None, "- Ngựa:", "- Horses:"),
    ("0101.21.00", "- - Loại thuần chủng để nhân giống", "- - Pure-bred breeding animals"),
    ("0101.29.00", "- - Loại khác", "- - Other"),
]


def _write(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    for _ in range(FIRST_DATA_ROW):
        sheet.append(["tiêu đề"])
    width = max(COLUMNS.values()) + 1
    for code, vi, en in rows:
        cells = [None] * width
        cells[COLUMNS["code"]], cells[COLUMNS["vi"]], cells[COLUMNS["en"]] = code, vi, en
        sheet.append(cells)
    workbook.save(path)
    return path


def test_parse_rows_builds_description_from_parents():
    rows, _ = parse_rows([r[:2] + (None,) for r in HORSES[:3]])
    assert [(r.code, r.chapter) for r in rows] == [("01012100", 1)]
    assert rows[0].description_vi == "Ngựa, lừa, la sống. > Ngựa: > Loại thuần chủng để nhân giống"


def test_parse_rows_skips_chapter_98_and_non_8_digit():
    rows, skipped = parse_rows([
        ("Chương 1", "Động vật sống", None),
        ("0101", "Ngựa, lừa, la sống.", None),
        ("0101.21", "- Ngựa:", None),
        ("0101.21.00", "- - Loại thuần chủng", None),
        ("9801", "Hàng đặc biệt", None),
        ("9801.00.10", "- Mặt hàng riêng", None),
        ("abc", "Không phải mã", None),
        ("0101.2", "- Mã 5 số", None),
    ])
    assert [r.code for r in rows] == ["01012100"]
    assert skipped == 1


def test_parse_rows_keeps_english_or_null():
    with_en, _ = parse_rows(HORSES)
    assert with_en[0].description_en == "Live horses, asses, mules > Horses: > Pure-bred breeding animals"
    without_en, _ = parse_rows([(c, v, None) for c, v, _ in HORSES])
    assert all(r.description_en is None for r in without_en)


def test_import_hs_is_idempotent_and_resets_embedding_on_change(db, tmp_path):
    path = _write(tmp_path / "tt31.xlsx", HORSES)
    first = import_hs(db, path)
    assert (first.inserted, first.updated) == (2, 0)
    again = import_hs(db, path)
    assert (again.inserted, again.updated) == (0, 0)

    row = db.get(HsCode, "01012100")
    row.embedding = [0.1] * 1024
    db.flush()
    changed = [r if r[0] != "0101.21.00" else (r[0], "- - Loại giống thuần chủng", r[2]) for r in HORSES]
    result = import_hs(db, _write(tmp_path / "tt31-v2.xlsx", changed))
    assert (result.inserted, result.updated) == (0, 1)
    db.refresh(row)
    assert row.embedding is None and "giống thuần chủng" in row.description_vi
    untouched = db.get(HsCode, "01012900")
    assert untouched.description_vi.endswith("Loại khác")


def test_vn_simple_matches_unaccented_query(db):
    matched = db.scalar(text("SELECT to_tsvector('vn_simple', 'Máy tính xách tay') "
                             "@@ plainto_tsquery('vn_simple', 'may tinh xach tay')"))
    assert matched is True
