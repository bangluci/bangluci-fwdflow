"""Mã tra cứu công khai: 10 ký tự Crockford base32 (không có I, L, O, U), in dạng XXXXX-XXXXX."""

import re
import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 10
_VALID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{10}$")
_LOOKALIKE = str.maketrans({"O": "0", "I": "1", "L": "1"})


def new_tracking_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(raw: str) -> str | None:
    """Chuẩn hoá thứ người dùng gõ: hoa, bỏ `-` / khoảng trắng, đổi ký tự dễ nhầm; sai định dạng thì `None`."""
    code = re.sub(r"[-\s]", "", raw.strip().upper()).translate(_LOOKALIKE)
    return code if _VALID.fullmatch(code) else None


def format_code(code: str) -> str:
    return f"{code[:5]}-{code[5:]}"
