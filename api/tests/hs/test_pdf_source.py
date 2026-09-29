from pathlib import Path

from fpdf import FPDF

from app.ai.hs.importer import import_hs, parse_rows
from app.ai.hs.models import HsCode
from app.ai.hs.pdf_source import read_pdf_rows

FONT = Path(__file__).resolve().parents[2] / "app" / "lastmile" / "fonts" / "DejaVuSans.ttf"


def make_pdf(path: Path, *pages: list[str]) -> Path:
    """Mỗi phần tử là một dòng vật lý trên trang, giống thứ tự đọc của PDF Công báo."""
    pdf = FPDF()
    pdf.add_font("DejaVu", fname=str(FONT))
    pdf.set_font("DejaVu", size=8)
    for lines in pages:
        pdf.add_page()
        for line in lines:
            pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    return path


def parse(path: Path) -> dict:
    rows, _ = parse_rows(read_pdf_rows(path))
    return {row.code: row for row in rows}


def test_pdf_rows_join_heading_subgroup_and_line_for_both_languages(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [
        "01.01 Ngựa, lừa, la sống 01.01 Live horses, asses, mules and hinnies",
        "- Ngựa: - Horses:",
        "0101.21.00 - - Loại thuần chủng để nhân giống kg/con 0101.21.00 - - Pure-bred breeding animals kg/unit",
        "0101.29.00 - - Loại khác kg/con 0101.29.00 - - Other kg/unit",
    ])
    rows = parse(pdf)
    assert rows["01012100"].description_vi == "Ngựa, lừa, la sống > Ngựa: > Loại thuần chủng để nhân giống"
    assert rows["01012100"].description_en == "Live horses, asses, mules and hinnies > Horses: > Pure-bred breeding animals"
    assert rows["01012900"].description_vi.endswith("> Loại khác")  # đơn vị `kg/con` đã bị bỏ


def test_pdf_mid_word_font_break_is_rejoined(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [
        "0101.29.00 - - Lo", "ại khác kg/con 0101.29.00 - - Other kg/unit",
    ])
    assert parse(pdf)["01012900"].description_vi == "Loại khác"


def test_pdf_heading_cell_wrapping_onto_a_line_that_starts_with_a_code(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [
        "03.02 Cá, tươi hoặc ướp lạnh, trừ phi-lê thuộc nhóm",
        "03.04 và các loại khác",
        "03.02 Fish, fresh or chilled, excluding fillets of heading 03.04",
        "0302.11.00 - - Cá hồi kg 0302.11.00 - - Trout kg",
    ])
    row = parse(pdf)["03021100"]
    assert row.description_vi == "Cá, tươi hoặc ướp lạnh, trừ phi-lê thuộc nhóm 03.04 và các loại khác > Cá hồi"
    assert row.description_en == "Fish, fresh or chilled, excluding fillets of heading 03.04 > Trout"


def test_pdf_chapter_note_lines_and_page_furniture_are_not_rows(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [
        "0101.29.00 - - Loại khác kg/con 0101.29.00 - - Other kg/unit",
        "39.13 trong các dung môi hữu cơ dễ bay hơi",
        "CÔNG BÁO/Số 533 + 534/Ngày 08-7-2022 Mã hàng Mô tả hàng hóa Đơn vị tính Code Description Unit of quantity",
        "Chương 2 Chapter 2",
        "0201.10.00 - - Thịt cả con kg 0201.10.00 - - Carcasses kg",
    ])
    rows = parse(pdf)
    assert set(rows) == {"01012900", "02011000"}
    assert rows["01012900"].description_en == "Other" and rows["02011000"].description_vi == "Thịt cả con"


def test_pdf_english_half_on_its_own_lines_is_paired_by_code(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [
        "28.50 Hydrua, nitrua, azit, silicua và borua",
        "28.50 Hydrides, nitrides, azides, silicides and borides",
        "2850.00.00 - Hydrua kg 2850.00.00 - Hydrides kg",
    ])
    row = parse(pdf)["28500000"]
    assert row.description_vi == "Hydrua, nitrua, azit, silicua và borua > Hydrua"
    assert row.description_en == "Hydrides, nitrides, azides, silicides and borides > Hydrides"


def test_pdf_directory_is_read_in_file_order_and_imported(db, tmp_path):
    make_pdf(tmp_path / "part-01.pdf", ["01.01 Ngựa 01.01 Horses", "0101.29.00 - - Loại khác kg 0101.29.00 - - Other kg"])
    make_pdf(tmp_path / "part-02.pdf", ["02.01 Thịt 02.01 Meat", "0201.10.00 - - Cả con kg 0201.10.00 - - Carcasses kg"])
    stats = import_hs(db, tmp_path)
    assert (stats.inserted, stats.updated) == (2, 0)
    assert db.get(HsCode, "02011000").description_vi == "Thịt > Cả con"
    assert import_hs(db, tmp_path).total == 0
