import pytest
from sqlalchemy import select

from app.auth.scope import get_scoped_or_404, scope_shipments
from app.catalog.models import Customer
from app.envelope import AppError
from app.shipments.models import Container, Shipment


@pytest.mark.parametrize("role", ["ADMIN", "DOCS", "DISPATCH", "ACCOUNTANT"])
def test_internal_roles_see_all_shipments(db, make_user, make_shipment, role):
    make_shipment()
    make_shipment()
    assert len(db.scalars(scope_shipments(select(Shipment.id), make_user(role))).all()) == 2


def test_customer_sees_only_own_shipments(db, make_user, make_shipment):
    customer_user = make_user("CUSTOMER")
    mine = make_shipment(customer=db.get(Customer, customer_user.customer_id))
    make_shipment()
    assert db.scalars(scope_shipments(select(Shipment.id), customer_user)).all() == [mine.id]


def test_driver_sees_no_shipments(db, make_user, make_shipment):
    make_shipment()
    assert db.scalars(scope_shipments(select(Shipment.id), make_user("DRIVER"))).all() == []


def test_get_scoped_or_404_other_customer(db, make_user, make_shipment):
    other = make_shipment()
    with pytest.raises(AppError) as err:
        get_scoped_or_404(db, Shipment, other.id, make_user("CUSTOMER"))
    assert err.value.status == 404


def test_not_owned_and_missing_same_error(db, make_user, make_shipment):
    other, user = make_shipment(), make_user("CUSTOMER")
    errors = []
    for shipment_id in (other.id, other.id + 10_000):
        with pytest.raises(AppError) as err:
            get_scoped_or_404(db, Shipment, shipment_id, user)
        errors.append((err.value.code, err.value.message, err.value.status))
    assert errors[0] == errors[1]


def test_container_scoped_through_shipment(db, make_user, make_shipment, make_container):
    customer_user = make_user("CUSTOMER")
    mine = make_container(make_shipment(customer=db.get(Customer, customer_user.customer_id)))
    theirs = make_container(make_shipment())
    assert get_scoped_or_404(db, Container, mine.id, customer_user).id == mine.id
    with pytest.raises(AppError):
        get_scoped_or_404(db, Container, theirs.id, customer_user)
