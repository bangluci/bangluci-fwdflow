from app.lastmile.service import packages_available


def test_packages_available_counts_active_orders(db, make_shipment, make_last_mile_order):
    shipment = make_shipment(status="AT_WAREHOUSE", total_packages=10)
    make_last_mile_order(shipment, 3, events=("CREATED",))
    make_last_mile_order(shipment, 2, events=("CREATED", "ASSIGNED", "PICKED_UP", "DELIVERED"))
    make_last_mile_order(shipment, 1, events=("CREATED", "ASSIGNED", "PICKED_UP", "FAILED"))
    assert packages_available(db, shipment) == 4


def test_packages_available_ignores_returned_and_cancelled(db, make_shipment, make_last_mile_order):
    shipment = make_shipment(status="AT_WAREHOUSE", total_packages=10)
    make_last_mile_order(shipment, 4, events=("CREATED", "CANCELLED"))
    make_last_mile_order(shipment, 3, events=("CREATED", "ASSIGNED", "PICKED_UP", "FAILED", "RETURNED"))
    assert packages_available(db, shipment) == 10
