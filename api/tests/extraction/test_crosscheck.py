import pytest

from app.ai.extraction.crosscheck import (
    BLOCK,
    DISCREPANCY,
    INSUFFICIENT,
    MATCH,
    WARN,
    crosscheck,
    normalize_company,
    token_set_ratio,
)


def _bl(**overrides):
    base = {"consignee": "CONG TY TNHH MINH LONG", "notify_party": None, "total_packages": 100,
            "gross_weight_kg": "1000.00",
            "containers": [{"container_no": "CSQU3054383", "seal_no": "S1"},
                           {"container_no": "TGHU1234567", "seal_no": "S2"}]}
    return {**base, **overrides}


def _pl(**overrides):
    base = {"total_packages": 100, "total_gross_weight_kg": "1000.00",
            "containers": [{"container_no": "csqu 3054383", "seal_no": "s1"},
                           {"container_no": "TGHU1234567", "seal_no": "S2"}]}
    return {**base, **overrides}


def _invoice(**overrides):
    return {**{"buyer": "Minh Long Co., Ltd"}, **overrides}


def _run(docs, is_fcl=True):
    return crosscheck(docs, is_fcl=is_fcl)


def _keys(result):
    return {(d.key, d.level) for d in result.discrepancies}


def test_single_approved_type_is_insufficient():
    assert _run({"HBL": _bl()}).status == INSUFFICIENT
    assert _run({}).status == INSUFFICIENT


def test_all_equal_is_match():
    result = _run({"HBL": _bl(), "PACKING_LIST": _pl(), "INVOICE": _invoice()})
    assert result.status == MATCH and result.discrepancies == []


def test_container_one_char_changed_is_block_fcl():
    pl = _pl(containers=[{"container_no": "CSQU3054384", "seal_no": "S1"}, {"container_no": "TGHU1234567",
                                                                              "seal_no": "S2"}])
    result = _run({"HBL": _bl(), "PACKING_LIST": pl})
    assert result.status == DISCREPANCY
    assert {("CONTAINER_SET:CSQU3054383", BLOCK), ("CONTAINER_SET:CSQU3054384", BLOCK)} <= _keys(result)


def test_missing_container_is_block_fcl():
    pl = _pl(containers=[{"container_no": "CSQU3054383", "seal_no": "S1"}])
    result = _run({"HBL": _bl(), "PACKING_LIST": pl})
    (only,) = result.discrepancies
    assert only.key == "CONTAINER_SET:TGHU1234567" and only.level == BLOCK
    assert only.values == {"HBL": "TGHU1234567", "PACKING_LIST": None}


def test_container_mismatch_is_warn_lcl():
    pl = _pl(containers=[{"container_no": "CSQU3054384", "seal_no": "S1"}])
    assert all(d.level == WARN for d in _run({"HBL": _bl(), "PACKING_LIST": pl}, is_fcl=False).discrepancies)


def test_seal_on_wrong_container_is_block_fcl():
    pl = _pl(containers=[{"container_no": "CSQU3054383", "seal_no": "S2"}, {"container_no": "TGHU1234567",
                                                                              "seal_no": "S1"}])
    result = _run({"HBL": _bl(), "PACKING_LIST": pl})
    assert {("SEAL:CSQU3054383", BLOCK), ("SEAL:TGHU1234567", BLOCK)} == _keys(result)


def test_missing_seal_is_not_a_mismatch():
    pl = _pl(containers=[{"container_no": "CSQU3054383", "seal_no": None}, {"container_no": "TGHU1234567",
                                                                            "seal_no": "S2"}])
    assert _run({"HBL": _bl(), "PACKING_LIST": pl}).status == MATCH


def test_packages_mismatch_is_warn():
    result = _run({"HBL": _bl(), "PACKING_LIST": _pl(total_packages=99)})
    assert _keys(result) == {("PACKAGES", WARN)}


def test_weight_diff_0_4_percent_ok():
    assert _run({"HBL": _bl(), "PACKING_LIST": _pl(total_gross_weight_kg="1004.00")}).status == MATCH


def test_weight_diff_0_6_percent_warn():
    result = _run({"HBL": _bl(), "PACKING_LIST": _pl(total_gross_weight_kg="1006.00")})
    assert _keys(result) == {("WEIGHT", WARN)}


def test_consignee_vi_en_same_company_matches():
    assert _run({"HBL": _bl(), "INVOICE": _invoice()}).status == MATCH


def test_consignee_to_order_uses_notify_party():
    hbl = _bl(consignee="TO ORDER OF SHIPPER", notify_party="MINH LONG CO., LTD")
    assert _run({"HBL": hbl, "INVOICE": _invoice()}).status == MATCH
    assert _keys(_run({"HBL": _bl(consignee="TO ORDER", notify_party="ABC TRADING"), "INVOICE": _invoice()})) == \
        {("CONSIGNEE", WARN)}


def test_consignee_different_company_warns():
    result = _run({"HBL": _bl(), "INVOICE": _invoice(buyer="Hoa Sen Group JSC")})
    assert _keys(result) == {("CONSIGNEE", WARN)}
    assert result.discrepancies[0].values == {"HBL": "CONG TY TNHH MINH LONG", "INVOICE": "Hoa Sen Group JSC"}


def test_mbl_consignee_is_not_compared():
    mbl = _bl(consignee="FORWARDER CO")
    assert _run({"MBL": mbl, "INVOICE": _invoice()}).status == MATCH


def test_lcl_ignores_mbl():
    mbl = _bl(containers=[{"container_no": "ZZZU0000000", "seal_no": "X"}], total_packages=5)
    assert _run({"MBL": mbl, "HBL": _bl()}, is_fcl=False).status == INSUFFICIENT
    assert _run({"MBL": mbl, "HBL": _bl(), "PACKING_LIST": _pl()}, is_fcl=False).status == MATCH
    assert _run({"MBL": mbl, "HBL": _bl()}, is_fcl=True).status == DISCREPANCY


@pytest.mark.parametrize(("raw", "expected"), [
    ("Công ty TNHH Xuất nhập khẩu Đông Á", "XUAT NHAP KHAU DONG A"),
    ("MINH LONG CO., LTD", "MINH LONG"),
    ("Cty CP Thực phẩm Hải Âu", "THUC PHAM HAI AU"),
    (None, ""),
])
def test_normalize_company_strips_legal_suffix_and_accents(raw, expected):
    assert normalize_company(raw) == expected


def test_token_set_ratio_ignores_order_and_extra_words():
    assert token_set_ratio("MINH LONG", "LONG MINH") == 1.0
    assert token_set_ratio("MINH LONG", "MINH LONG TRADING") >= 0.85
    assert token_set_ratio("", "MINH") == 0.0
