import re

from app.lastmile.tracking_code import format_code, new_tracking_code, normalize_code


def test_new_code_is_10_crockford_chars():
    pattern = re.compile(r"^[0-9A-HJKMNP-TV-Z]{10}$")
    assert all(pattern.fullmatch(new_tracking_code()) for _ in range(1000))


def test_normalize_maps_ambiguous_chars():
    assert normalize_code("dem0o-track") == "DEM00TRACK"
    assert normalize_code("ilIL234567") == "1111234567"
    assert normalize_code(" dem00 track ") == "DEM00TRACK"


def test_normalize_rejects_u_and_wrong_length():
    assert normalize_code("UUUUU11111") is None and normalize_code("ABC") is None


def test_format_code_groups_of_five():
    assert format_code("DEM00TRACK") == "DEM00-TRACK"
