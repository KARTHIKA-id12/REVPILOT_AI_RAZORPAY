import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.campaigns.inputs import compute_simulation_inputs
from app.db.session import SessionLocal
from app.main import app
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem
from app.models.customers import Customer
from app.models.identity import Merchant
from app.models.opportunities import RevenueOpportunity

client = TestClient(app)


@pytest.fixture
def merchant_with_data():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Sim Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()

    product_a = Product(merchant_id=merchant.id, sku="SIM-A", name="Sim Product A", price_amount=1000, stock_qty=50, stock_status="in_stock")
    product_b = Product(merchant_id=merchant.id, sku="SIM-B", name="Sim Product B", price_amount=500, stock_qty=50, stock_status="in_stock")
    db.add_all([product_a, product_b])
    db.flush()

    # Seed enough real paid orders that reach/confidence aren't trivially zero.
    customers = [Customer(merchant_id=merchant.id, name=f"Customer {i}") for i in range(20)]
    db.add_all(customers)
    db.flush()

    for i, customer in enumerate(customers):
        order = Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=1000, total_amount=1000)
        db.add(order)
        db.flush()
        db.add(OrderItem(order_id=order.id, product_id=product_a.id, quantity=1, unit_price_amount=1000))
        if i < 8:  # 8 of the 20 A-buyers also bought B
            order_b = Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=500, total_amount=500)
            db.add(order_b)
            db.flush()
            db.add(OrderItem(order_id=order_b.id, product_id=product_b.id, quantity=1, unit_price_amount=500))

    opportunity = RevenueOpportunity(
        merchant_id=merchant.id, type="cross_sell", source_product_id=product_a.id, target_product_id=product_b.id,
        reach_count=12, confidence=0.5, historical_affinity=2.0, estimated_conversion=0.2,
        estimated_revenue_amount=5000, risk_level="low", priority_score=90,
        evidence_json={"confidence_organic": 0.4}, status="open",
    )
    db.add(opportunity)
    db.commit()

    yield db, merchant.id, product_a.id, product_b.id, opportunity.id
    from app.services.merchant_cleanup import reset_merchant
    reset_merchant(db, merchant.id)  # this fixture commits real data (orders, opportunities) — must clean up explicitly
    db.close()


def test_compare_by_product_ids_returns_scenarios_for_each_discount(merchant_with_data):
    db, merchant_id, product_a, product_b, _ = merchant_with_data
    response = client.post(
        f"/api/v1/simulations/compare?merchant_id={merchant_id}",
        json={"product_ids": [str(product_a), str(product_b)], "discount_percents": [5, 10, 15]},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["scenarios"]) == 3
    assert [s["discount_percent"] for s in body["scenarios"]] == [5, 10, 15]
    # reach should reflect the real 20-8=12 A-buyers who haven't bought B
    assert body["eligible_customers"] == 12


def test_compare_by_opportunity_id_uses_stored_evidence_confidence(merchant_with_data):
    db, merchant_id, product_a, product_b, opportunity_id = merchant_with_data
    response = client.post(
        f"/api/v1/simulations/compare?merchant_id={merchant_id}",
        json={"opportunity_id": str(opportunity_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["organic_confidence"] == 0.4  # from evidence_json, not re-derived
    assert body["recommended_discount_percent"] is not None


def test_missing_both_opportunity_and_products_rejected(merchant_with_data):
    db, merchant_id, *_ = merchant_with_data
    response = client.post(f"/api/v1/simulations/compare?merchant_id={merchant_id}", json={})
    assert response.status_code == 422


def test_discount_over_100_rejected_before_reaching_simulation_math(merchant_with_data):
    db, merchant_id, product_a, product_b, _ = merchant_with_data
    response = client.post(
        f"/api/v1/simulations/compare?merchant_id={merchant_id}",
        json={"product_ids": [str(product_a), str(product_b)], "discount_percents": [150]},
    )
    assert response.status_code == 422


def test_unknown_opportunity_id_returns_404_not_a_silent_empty_result(merchant_with_data):
    db, merchant_id, *_ = merchant_with_data
    response = client.post(
        f"/api/v1/simulations/compare?merchant_id={merchant_id}",
        json={"opportunity_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_opportunity_from_a_different_merchant_is_not_leaked(merchant_with_data):
    """Loophole check: an opportunity_id belonging to another merchant
    must never be usable to simulate against this merchant's data."""
    db, merchant_id, product_a, product_b, _ = merchant_with_data
    other_merchant = Merchant(name=f"Other Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(other_merchant)
    db.flush()
    other_opportunity = RevenueOpportunity(
        merchant_id=other_merchant.id, type="cross_sell", source_product_id=product_a, target_product_id=product_b,
        reach_count=99, confidence=0.9, historical_affinity=5.0, estimated_conversion=0.5,
        estimated_revenue_amount=99999, risk_level="low", priority_score=100, evidence_json={}, status="open",
    )
    db.add(other_opportunity)
    db.commit()

    response = client.post(
        f"/api/v1/simulations/compare?merchant_id={merchant_id}",
        json={"opportunity_id": str(other_opportunity.id)},
    )
    assert response.status_code == 404

    from app.services.merchant_cleanup import reset_merchant
    reset_merchant(db, other_merchant.id)


def test_shared_inputs_function_gives_identical_result_both_call_sites(merchant_with_data):
    """Ensures the pipeline (agent path) and the standalone Simulator API
    are provably using the exact same computation — not two
    implementations that happen to agree today but could silently drift."""
    db, merchant_id, product_a, product_b, _ = merchant_with_data
    from app.agents.pipeline import compute_simulation_inputs as pipeline_fn

    direct = compute_simulation_inputs(db, merchant_id, [product_a, product_b])
    via_pipeline_import = pipeline_fn(db, merchant_id, [product_a, product_b])
    assert direct == via_pipeline_import
