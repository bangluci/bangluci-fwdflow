import pytest

from app.freetime.tiers import TierConfigError, TierIn, validate_fee_type_set, validate_tiers


def tier(from_day, to_day=None, rate=1000, currency="USD"):
    return TierIn(from_day, to_day, rate, currency)


@pytest.mark.parametrize(("free_days", "tiers"), [
    (5, [tier(6)]),
    (5, [tier(6, 10), tier(11)]),
    (0, [tier(1)]),
])
def test_valid_tiers_accepted(free_days, tiers):
    validate_tiers(free_days, tiers)


def test_tiers_input_order_does_not_matter():
    validate_tiers(5, [tier(11), tier(6, 10)])


@pytest.mark.parametrize(("free_days", "tiers", "reason"), [
    (5, [], "EMPTY"),
    (5, [tier(7)], "FIRST_TIER_START"),
    (5, [tier(5)], "FIRST_TIER_START"),
    (5, [tier(6, 10), tier(12)], "GAP"),
    (5, [tier(6, 10), tier(10)], "OVERLAP"),
    (5, [tier(6), tier(11)], "OPEN_TIER_NOT_LAST"),
    (5, [tier(6, 10)], "LAST_TIER_CLOSED"),
    (5, [tier(6, 10), tier(11, currency="VND")], "MIXED_CURRENCY"),
    (5, [tier(6, rate=-1)], "BAD_VALUE"),
    (5, [tier(6, currency="EUR")], "BAD_VALUE"),
    (5, [tier(6, 4)], "BAD_VALUE"),
])
def test_reject_bad_tiers(free_days, tiers, reason):
    with pytest.raises(TierConfigError) as err:
        validate_tiers(free_days, tiers)
    assert err.value.code == "INVALID_TIERS" and err.value.status == 400
    assert err.value.details["reason"] == reason and err.value.message


def test_error_reports_index_of_bad_tier_in_sorted_order():
    with pytest.raises(TierConfigError) as err:
        validate_tiers(5, [tier(12), tier(6, 10)])
    assert err.value.details == {"reason": "GAP", "index": 1}


@pytest.mark.parametrize("fee_types", [["COMBINED"], ["DEM", "DET"], ["DET", "DEM"]])
def test_valid_fee_type_sets(fee_types):
    validate_fee_type_set(fee_types)


@pytest.mark.parametrize("fee_types", [["COMBINED", "DEM"], ["COMBINED", "DET"], ["COMBINED", "DEM", "DET"]])
def test_reject_combined_with_dem_det_same_date(fee_types):
    with pytest.raises(TierConfigError) as err:
        validate_fee_type_set(fee_types)
    assert err.value.code == "INVALID_RULE_SET" and err.value.details["reason"] == "MIXED_COMBINED"


@pytest.mark.parametrize(("fee_types", "reason"), [
    ([], "EMPTY"), (["DEM"], "INCOMPLETE_PAIR"), (["DET"], "INCOMPLETE_PAIR"), (["DEM", "DEM"], "DUPLICATE_FEE_TYPE"),
])
def test_reject_incomplete_or_duplicate_fee_type_sets(fee_types, reason):
    with pytest.raises(TierConfigError) as err:
        validate_fee_type_set(fee_types)
    assert err.value.details["reason"] == reason
