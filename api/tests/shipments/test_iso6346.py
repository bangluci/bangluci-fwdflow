import pytest

from app.shipments.iso6346 import container_check_digit, is_valid_container_no, normalize_container_no


@pytest.mark.parametrize(("prefix", "digit"), [("CSQU305438", 3), ("MSKU907032", 3), ("TGHU123456", 7)])
def test_check_digit_known_numbers(prefix, digit):
    assert container_check_digit(prefix) == digit


def test_check_digit_remainder_10_is_0():
    assert container_check_digit("MSCU000006") == 0


def test_valid_accepts_spaces_hyphen_lowercase():
    assert is_valid_container_no("csqu 305438-3")
    assert normalize_container_no("csqu 305438-3") == "CSQU3054383"


def test_invalid_check_digit():
    assert not is_valid_container_no("CSQU3054384")


@pytest.mark.parametrize("number", ["CSQ3054383", "CSQU305438", "CSQX3054383", "CSQU30543830"])
def test_invalid_format(number):
    assert not is_valid_container_no(number)
