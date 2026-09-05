import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.agents.pipeline import create_campaign_draft, decide_approval, request_campaign_approval
from app.agents.schemas import CreateCampaignDraftInput, RequestCampaignApprovalInput
from app.agents.service import create_session
from app.db.session import SessionLocal
from app.main import app
from app.models.campaigns import AgentPermission, Campaign, PolicyRule
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem
from app.models.customers import Customer
from app.models.identity import Merchant, MerchantSettings
from app.services.merchant_cleanup import reset_merchant

client = TestClient(app)


@pytest.fixture
def merchant_with_running_campaign():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Campaign Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))
    for code, value in {"MAX_DISCOUNT_PERCENT": 15, "MAX_CAMPAIGN_BUDGET": 5000, "NO_OUT_OF_STOCK_PRODUCTS": True}.items():
        db.add(PolicyRule(merchant_id=merchant.id, code=code, value_json={"value": value}))
    for code, mode in {"CREATE_CAMPAIGN_DRAFT": "ALLOW", "CREATE_DISCOUNT": "APPROVAL"}.items():
        db.add(AgentPermission(merchant_id=merchant.id, action_code=code, mode=mode))

    product_a = Product(merchant_id=merchant.id, sku="CAMP-A", name="Campaign Product A", price_amount=1000, stock_qty=50, stock_status="in_stock")
    product_b = Product(merchant_id=merchant.id, sku="CAMP-B", name="Campaign Product B", price_amount=500, stock_qty=50, stock_status="in_stock")
    db.add_all([product_a, product_b])
    db.flush()

    for i in range(10):
        customer = Customer(merchant_id=merchant.id, name=f"Campaign Customer {i}")
        db.add(customer)
        db.flush()
        order = Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=1000, total_amount=1000)
        db.add(order)
        db.flush()
        db.add(OrderItem(order_id=order.id, product_id=product_a.id, quantity=1, unit_price_amount=1000))
    db.flush()

    session = create_session(db, merchant.id, user_id=None)
    draft = create_campaign_draft(db, merchant.id, session.id, CreateCampaignDraftInput(
        name="Campaign View Test", objective="cross_sell", product_ids=[product_a.id, product_b.id],
        discount_percent=10, budget_amount=1000,
    ))
    campaign_id = uuid.UUID(draft.result_json["campaign_id"])
    approval_action = request_campaign_approval(db, merchant.id, session.id, RequestCampaignApprovalInput(campaign_id=campaign_id))
    decide_approval(db, merchant.id, approval_action.approval_id, "approve", decided_by_user_id=None)
    db.commit()

    yield db, merchant.id, campaign_id
    reset_merchant(db, merchant.id)
    db.close()


def test_list_campaigns_returns_the_created_campaign(merchant_with_running_campaign):
    db, merchant_id, campaign_id = merchant_with_running_campaign
    response = client.get(f"/api/v1/campaigns?merchant_id={merchant_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(campaign_id)
    assert body["items"][0]["status"] == "running"


def test_campaign_detail_includes_full_history(merchant_with_running_campaign):
    db, merchant_id, campaign_id = merchant_with_running_campaign
    response = client.get(f"/api/v1/campaigns/{campaign_id}")
    assert response.status_code == 200
    body = response.json()

    assert len(body["products"]) == 2
    assert len(body["approval_history"]) == 1
    assert body["approval_history"][0]["status"] == "approved"
    assert len(body["payments"]) == 1
    assert body["payments"][0]["provider"] == "mock"
    # Audit trail must show the full lifecycle: draft, approval request,
    # approval decision, execution — not just the final state.
    actions_seen = {e["action"] for e in body["audit_trail"]}
    assert "CREATE_DISCOUNT" in actions_seen
    assert "CREATE_PAYMENT_LINK" in actions_seen


def test_pause_only_valid_from_running_status(merchant_with_running_campaign):
    db, merchant_id, campaign_id = merchant_with_running_campaign
    response = client.post(f"/api/v1/campaigns/{campaign_id}/pause")
    assert response.status_code == 200
    assert response.json()["status"] == "paused"

    # Pausing an already-paused campaign is not a valid transition.
    second = client.post(f"/api/v1/campaigns/{campaign_id}/pause")
    assert second.status_code == 409


def test_cancel_from_paused_succeeds(merchant_with_running_campaign):
    db, merchant_id, campaign_id = merchant_with_running_campaign
    client.post(f"/api/v1/campaigns/{campaign_id}/pause")
    response = client.post(f"/api/v1/campaigns/{campaign_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # Cancelling an already-cancelled campaign is rejected, not a silent no-op.
    second = client.post(f"/api/v1/campaigns/{campaign_id}/cancel")
    assert second.status_code == 409


def test_unknown_campaign_returns_404():
    response = client.get(f"/api/v1/campaigns/{uuid.uuid4()}")
    assert response.status_code == 404


def test_campaign_from_another_merchant_not_leaked_in_list(merchant_with_running_campaign):
    """Loophole check: listing campaigns for merchant A must never
    include merchant B's campaigns, even if queried without a status filter."""
    db, merchant_id, campaign_id = merchant_with_running_campaign
    other = Merchant(name=f"Other Campaign Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(other)
    db.flush()
    db.add(Campaign(merchant_id=other.id, name="Other merchant campaign", objective="cross_sell", discount_percent=5, budget_amount=100, status="draft"))
    db.commit()

    response = client.get(f"/api/v1/campaigns?merchant_id={merchant_id}")
    names = {c["name"] for c in response.json()["items"]}
    assert "Other merchant campaign" not in names

    reset_merchant(db, other.id)
