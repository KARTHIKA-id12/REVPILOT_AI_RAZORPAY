import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app
from app.models.campaigns import AgentPermission, Campaign, PolicyRule
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem
from app.models.customers import Customer
from app.models.identity import Merchant, MerchantSettings
from app.services.failure_injection import is_armed
from app.services.merchant_cleanup import reset_merchant

client = TestClient(app)


@pytest.fixture
def merchant_with_data():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"FailureLab Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))
    for code, value in {"MAX_DISCOUNT_PERCENT": 15, "MAX_CAMPAIGN_BUDGET": 5000, "NO_OUT_OF_STOCK_PRODUCTS": True}.items():
        db.add(PolicyRule(merchant_id=merchant.id, code=code, value_json={"value": value}))
    for code, mode in {"CREATE_CAMPAIGN_DRAFT": "ALLOW", "CREATE_DISCOUNT": "APPROVAL"}.items():
        db.add(AgentPermission(merchant_id=merchant.id, action_code=code, mode=mode))

    product_a = Product(merchant_id=merchant.id, sku="FL-A", name="FailLab Product A", price_amount=1000, stock_qty=50, stock_status="in_stock")
    product_b = Product(merchant_id=merchant.id, sku="FL-B", name="FailLab Product B", price_amount=500, stock_qty=50, stock_status="in_stock")
    db.add_all([product_a, product_b])
    db.flush()

    for i in range(10):
        customer = Customer(merchant_id=merchant.id, name=f"FailLab Customer {i}")
        db.add(customer)
        db.flush()
        order = Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=1000, total_amount=1000)
        db.add(order)
        db.flush()
        db.add(OrderItem(order_id=order.id, product_id=product_a.id, quantity=1, unit_price_amount=1000))
        if i < 3:  # a few also bought product B, giving the simulation a genuine non-zero organic_confidence
            order_b = Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=500, total_amount=500)
            db.add(order_b)
            db.flush()
            db.add(OrderItem(order_id=order_b.id, product_id=product_b.id, quantity=1, unit_price_amount=500))
    db.commit()

    yield db, merchant.id, product_a.id, product_b.id
    reset_merchant(db, merchant.id)
    db.close()


def test_payment_provider_error_scenario_detects_fails_and_recovers(merchant_with_data):
    db, merchant_id, product_a, product_b = merchant_with_data
    response = client.post(f"/api/v1/demo/failures/payment_provider_error?merchant_id={merchant_id}")
    assert response.status_code == 200
    body = response.json()

    stages = [t["stage"] for t in body["trace"]]
    assert "DETECTED" in stages
    assert "PROTECTED" in stages
    assert "RECOVERED" in stages

    # The injector must have consumed its single shot - nothing left armed.
    assert is_armed(merchant_id) is False

    # The campaign must have genuinely recovered to 'running', not just
    # claimed to in the trace text.
    campaign = db.get(Campaign, uuid.UUID(body["campaign_id"]))
    assert campaign.status == "running"


def test_payment_timeout_scenario_uses_real_timeout_exception(merchant_with_data):
    db, merchant_id, product_a, product_b = merchant_with_data
    response = client.post(f"/api/v1/demo/failures/payment_timeout?merchant_id={merchant_id}")
    assert response.status_code == 200
    stages_with_status = {t["stage"]: t["status"] for t in response.json()["trace"]}
    assert stages_with_status["DETECTED"] == "failure"
    assert stages_with_status["RECOVERED"] == "ok"


def test_duplicate_webhook_scenario_proves_revenue_counted_once(merchant_with_data):
    db, merchant_id, product_a, product_b = merchant_with_data
    response = client.post(f"/api/v1/demo/failures/duplicate_webhook?merchant_id={merchant_id}")
    assert response.status_code == 200
    body = response.json()
    verified = next(t for t in body["trace"] if t["stage"] == "VERIFIED")
    assert verified["status"] == "ok"

    campaign = db.get(Campaign, uuid.UUID(body["campaign_id"]))
    db.refresh(campaign)
    # Exactly the campaign's expected revenue, not double-counted. (With
    # a genuinely non-zero simulated revenue, actual == expected exactly;
    # this fixture is deliberately built with real cross-purchase data so
    # this isn't hitting the separate 'never create a ₹0 payment link'
    # fallback edge case, which is correct-but-different behavior.)
    assert float(campaign.actual_revenue_amount) == float(campaign.expected_revenue_amount)
    assert float(campaign.actual_revenue_amount) > 0


def test_invalid_discount_scenario_genuinely_blocks_via_policy_engine(merchant_with_data):
    db, merchant_id, product_a, product_b = merchant_with_data
    response = client.post(f"/api/v1/demo/failures/invalid_discount?merchant_id={merchant_id}")
    assert response.status_code == 200
    body = response.json()
    policy_check = next(t for t in body["trace"] if t["stage"] == "POLICY CHECK")
    assert policy_check["status"] == "blocked"
    assert "15" in policy_check["detail"]  # the actual configured cap appears in the real error message

    campaign = db.get(Campaign, uuid.UUID(body["campaign_id"]))
    assert campaign.status == "draft"  # never advanced — proves it was genuinely blocked, not simulated


def test_out_of_stock_scenario_restores_real_stock_status_afterward(merchant_with_data):
    db, merchant_id, product_a, product_b = merchant_with_data
    response = client.post(f"/api/v1/demo/failures/out_of_stock?merchant_id={merchant_id}")
    assert response.status_code == 200
    body = response.json()
    stock_check = next(t for t in body["trace"] if t["stage"] == "STOCK CHECK")
    assert stock_check["status"] == "blocked"

    # Critical: the demo must not leave real catalog data corrupted.
    product = db.get(Product, product_b)
    db.refresh(product)
    assert product.stock_status == "in_stock"


def test_permission_denied_scenario_restores_real_permission_afterward(merchant_with_data):
    db, merchant_id, product_a, product_b = merchant_with_data
    response = client.post(f"/api/v1/demo/failures/permission_denied?merchant_id={merchant_id}")
    assert response.status_code == 200
    body = response.json()
    perm_check = next(t for t in body["trace"] if t["stage"] == "PERMISSION CHECK")
    assert perm_check["status"] == "blocked"

    # Critical: the demo must not leave real merchant settings corrupted.
    permission = db.query(AgentPermission).filter(
        AgentPermission.merchant_id == merchant_id, AgentPermission.action_code == "CREATE_CAMPAIGN_DRAFT"
    ).one()
    assert permission.mode == "ALLOW"


def test_unknown_scenario_rejected():
    response = client.post(f"/api/v1/demo/failures/not_a_real_scenario?merchant_id={uuid.uuid4()}")
    assert response.status_code == 422


def test_scenarios_list_endpoint():
    response = client.get("/api/v1/demo/failures/scenarios")
    assert response.status_code == 200
    codes = {s["code"] for s in response.json()["scenarios"]}
    assert "payment_timeout" in codes
    assert "duplicate_webhook" in codes
