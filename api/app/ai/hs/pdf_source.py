"""Đọc Danh mục TT 31/2022 từ các file PDF của Công báo (nguồn chính thức chỉ có PDF/DOC, không có xlsx).

Mỗi dòng bảng có hai nửa cạnh nhau: `mã | mô tả VI | đơn vị | mã | mô tả EN | đơn vị`. Văn bản do pdfium trả về
theo thứ tự đọc nên mã xuất hiện hai lần trên một dòng; ta tách đôi ở lần lặp thứ hai. Dòng phân nhóm không có mã
(`- Ngựa:`) thì lặp lại dãy gạch đầu dòng. Các lỗi của nguồn được xử lý: ngắt dòng giữa từ khi đổi font (`Lo⏎ại`),
dòng chú giải chương bắt đầu bằng mã, ghi chú `(SEN)`, đơn vị tính dính vào chữ cuối.
"""

import re
from pathlib import Path

import pypdfium2 as pdfium

Row = tuple[str | None, str, str | None]  # (mã hoặc None cho dòng phân nhóm, mô tả VI, mô tả EN)

# `39.16` (nhóm), `3916.10` (phân nhóm), `3916.10.10` (dòng hàng)
CODE_START = re.compile(r"^(\d{2}\.\d{2}|\d{4}\.\d{2}(?:\.\d{2})?)(?=\s|$)")
DASH_START = re.compile(r"^((?:-\s*)+)(?=\S)")
# ngắt dòng giữa từ: không có khoảng trắng đứng trước, chữ kế tiếp có dấu (trừ đ/Đ, chúng mở đầu từ thật)
_MID_WORD_BREAK = re.compile(r"(?<=\S)\n(?=[À-ďĒ-ỹ])")
_PAGE_NOISE = re.compile(r"CÔNG BÁO|Unit of quantity|^Mã hàng|^\d{1,3}$")
_SECTION_TITLE = re.compile(r"^(PHÂN CHƯƠNG|CHƯƠNG|Chương|PHẦN|Phần|SECTION|Chapter|SUB-CHAPTER)\b")
_SEN_FOOTNOTE = re.compile(r"\(SEN\):.*$")
_VALID_START = re.compile(r"^(-|[A-ZÀ-ỸĐ])")  # mô tả thật bắt đầu bằng gạch đầu dòng hoặc chữ hoa
_BROKEN_UNIT = re.compile(r"chiế\s+c\b")

_EN_UNIT = r"(?:kg|g|unit|liter|m|m2|m3|pair|set|carat|kWh)"
_VI_UNIT = r"(?:kg|g|chiếc|lít|bộ|đôi|con|cành|cây|quả|cuốn|hộp|m|m2|m3|carat|kWh)"
_EN_UNIT_TAIL = re.compile(rf"\s{_EN_UNIT}(?:/{_EN_UNIT})*$")
_VI_UNIT_TAIL = re.compile(rf"\s{_VI_UNIT}(?:/{_VI_UNIT})*$")
_SI_UNITS = frozenset({"kg", "g", "m", "m2", "m3", "carat", "kWh"})


def _page_lines(page: "pdfium.PdfPage") -> list[str]:
    raw = page.get_textpage().get_text_range().replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in _MID_WORD_BREAK.sub("", raw).split("\n") if line.strip()]


def _marker(line: str) -> tuple[str, str] | None:
    """(khoá dòng, phần còn lại). Dòng phân nhóm không mã có khoá là dãy gạch (`-`, `- -`), chuẩn hoá khoảng trắng."""
    code = CODE_START.match(line)
    if code:
        return code.group(1), line
    dashes = DASH_START.match(line)
    if dashes:
        key = " ".join("-" * dashes.group(1).count("-"))
        return key, f"{key} {line[dashes.end():]}"
    return None


def _marker_pattern(key: str) -> str:
    if key.startswith("-"):
        return r"(?<=\s)" + re.escape(key) + r"(?=\s)"
    return r"\s*".join(re.escape(char) for char in key)


def _split_halves(key: str, text: str) -> tuple[str, str] | None:
    """Tách theo lần lặp thứ hai của khoá: (nửa VI, nửa EN), đều đã bỏ khoá đầu."""
    body = text[len(key):]
    match = re.search(_marker_pattern(key), body)
    if match is None:
        return None
    return body[:match.start()].strip(), body[match.end():].strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _SEN_FOOTNOTE.sub("", text).replace("(SEN)", "")).strip()


def _is_open(row: list) -> bool:
    """Dòng chưa thấy nửa tiếng Anh (mã chưa lặp lại)."""
    return _split_halves(row[0], _clean(" ".join(row[1]))) is None


def _reopened_index(rows: list[list], key: str) -> int | None:
    """Dòng còn mở gần nhất có cùng khoá mà mọi "dòng" nằm giữa cũng còn mở và có mã (mảnh của ô VI bị ngắt); dòng
    phân nhóm không mã chỉ ghép với dòng ngay trước."""
    for index in range(len(rows) - 1, max(len(rows) - 5, -1), -1):
        if rows[index][0] == key and _is_open(rows[index]):
            between = rows[index + 1:]
            if all(_is_open(row) and not row[0].startswith("-") for row in between) and not (
                    key.startswith("-") and between):
                return index
            return None
    return None


def _collect_rows(pages: list[list[str]]) -> list[tuple[str, str]]:
    """Gom các dòng vật lý thành từng dòng bảng (khoá, văn bản thô). Nửa tiếng Anh bắt đầu bằng khoá lặp lại vẫn thuộc
    dòng cũ nếu dòng cũ chưa đủ hai nửa. Ô mô tả VI xuống dòng có thể bắt đầu bằng một mã (`... thuộc nhóm` ⏎
    `03.04.`): khi khoá của nửa EN quay lại một dòng còn mở ngay phía trước, các "dòng" nằm giữa được nhập lại."""
    rows: list[list] = []
    for lines in pages:
        current = None
        for line in lines:
            found = _marker(line)
            if found:
                reopened = _reopened_index(rows, found[0])
                if reopened is not None:
                    for between in rows[reopened + 1:]:
                        rows[reopened][1].extend(between[1])
                    del rows[reopened + 1:]
                    rows[reopened][1].append(found[1])
                    current = rows[reopened]
                else:
                    current = [found[0], [found[1]]]
                    rows.append(current)
            elif _SECTION_TITLE.match(line):
                current = None
            elif _PAGE_NOISE.search(line):
                continue
            elif current is not None:
                current[1].append(line)
    return [(key, re.sub(r"\s+", " ", " ".join(lines)).strip()) for key, lines in rows]


def _strip_unit(vi: str, en: str) -> tuple[str, str]:
    """Bỏ cột đơn vị tính ở cuối mỗi nửa, chỉ khi nửa EN kết thúc bằng đơn vị đã biết (dòng phân nhóm không có)."""
    tail = _EN_UNIT_TAIL.search(en)
    if tail is None:
        return vi, en
    unit_en = tail.group().strip()
    vi = _BROKEN_UNIT.sub("chiếc", vi)
    vi_tail = _VI_UNIT_TAIL.search(vi)
    if vi_tail:
        vi = vi[:vi_tail.start()].strip()
    elif unit_en in _SI_UNITS and vi.endswith(unit_en):  # đơn vị dính vào chữ cuối, ví dụ `đầum3`
        vi = vi[:-len(unit_en)].strip()
    return vi, en[:tail.start()].strip()


def _row(key: str, vi: str, en: str) -> Row | None:
    if key.startswith("-"):  # dòng phân nhóm không mã: trả lại gạch đầu dòng để `parse_rows` biết cấp
        return (None, f"{key} {vi}", f"{key} {en}" if en else None) if vi else None
    if not _VALID_START.match(vi):
        return None
    vi, en = _strip_unit(vi, en) if len(key.replace(".", "")) == 8 else (vi, en)
    return key, vi, en or None


def read_pdf_rows(source: Path) -> list[Row]:
    """`(mã, mô tả VI có gạch đầu dòng, mô tả EN)` theo thứ tự trong văn bản, đúng dạng `importer.parse_rows` nhận."""
    files = [source] if source.is_file() else sorted(source.glob("*.pdf"))
    pages: list[list[str]] = []
    for path in files:
        document = pdfium.PdfDocument(str(path))
        try:
            pages.extend(_page_lines(document[index]) for index in range(len(document)))
        finally:
            document.close()
    complete: list[tuple[int, Row]] = []
    lonely: dict[str, list[tuple[int, str]]] = {}
    for position, (key, raw) in enumerate(_collect_rows(pages)):
        text = _clean(raw)
        halves = _split_halves(key, text)
        if halves is not None:
            row = _row(key, *halves)
            if row is not None:
                complete.append((position, row))
        elif not key.startswith("-") and _VALID_START.match(text[len(key):].strip()):
            lonely.setdefault(key, []).append((position, text[len(key):].strip()))
    known = {row[0] for _, row in complete}
    for key, parts in lonely.items():  # VI và EN nằm ở hai dòng cách nhau: ghép lại tại vị trí của mảnh đầu
        if key not in known and len(parts) <= 2:
            complete.append((parts[0][0], (key, parts[0][1], parts[1][1] if len(parts) == 2 else None)))
    return [row for _, row in sorted(complete, key=lambda item: item[0])]
