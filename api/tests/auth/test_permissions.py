import pytest

from app.auth.models import Role
from app.auth.permissions import PERMISSIONS, can

EXTERNAL_ONLY = {"portal.read", "driver.act"}


@pytest.mark.parametrize("action", sorted(set(PERMISSIONS) - EXTERNAL_ONLY))
def test_internal_actions_exclude_customer_and_driver(action):
    assert not can(Role.CUSTOMER, action) and not can(Role.DRIVER, action)


def test_admin_has_every_action_except_portal_and_driver():
    assert {a for a in PERMISSIONS if can(Role.ADMIN, a)} == set(PERMISSIONS) - EXTERNAL_ONLY


def test_external_actions_belong_to_one_role_only():
    assert PERMISSIONS["portal.read"] == {Role.CUSTOMER} and PERMISSIONS["driver.act"] == {Role.DRIVER}


def test_shipment_write_split_between_docs_and_dispatch():
    assert can(Role.DOCS, "shipment.write") and not can(Role.DISPATCH, "shipment.write")
    assert can(Role.DISPATCH, "transport.write") and not can(Role.DOCS, "transport.write")
    assert not can(Role.ACCOUNTANT, "shipment.write")
