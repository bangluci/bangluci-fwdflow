"""ISO 6346: số container = 3 chữ cái chủ sở hữu + `U` + 6 chữ số + 1 chữ số kiểm tra."""

import re
import string

_FORMAT = re.compile(r"[A-Z]{3}U[0-9]{7}")


def _letter_values() -> dict[str, int]:
    """A=10, B=12, C=13, ...: bỏ qua các bội của 11 (11, 22, 33)."""
    values, current = {}, 10
    for letter in string.ascii_uppercase:
        if current % 11 == 0:
            current += 1
        values[letter] = current
        current += 1
    return values


_VALUES = _letter_values()


def container_check_digit(prefix10: str) -> int:
    """Chữ số kiểm tra từ 10 ký tự đầu (4 chữ cái + 6 chữ số)."""
    total = sum((_VALUES[c] if c.isalpha() else int(c)) * 2**i for i, c in enumerate(prefix10))
    return total % 11 % 10


def normalize_container_no(raw: str) -> str:
    return raw.upper().replace(" ", "").replace("-", "")


def is_valid_container_no(raw: str) -> bool:
    number = normalize_container_no(raw)
    return bool(_FORMAT.fullmatch(number)) and int(number[10]) == container_check_digit(number[:10])
