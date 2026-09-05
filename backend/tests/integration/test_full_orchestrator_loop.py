"""Phase 14 - Campaign Orchestrator, closed out properly.

This is the single test that asserts the ENTIRE product loop end to end,
in one place, rather than trusting that it works because scattered
phase-specific tests each cover a fragment of it:

    Opportunity -> Agent -> Simulation -> Policy -> Approval
    -> Razorpay -> Webhook -> Attribution

Every prior phase (7, 10, 12) exercised pieces of this chain in isolation
or via ad-hoc manual HTTP testing during development. This test exists so
the full chain has a permanent, explicit assertion of its own - the kind
of test that would catch a future refactor silently breaking the seam
between any two stages, which no single phase's test suite would notice
on its own.
"""

import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.agents.pipeline import create_campaign_draft, decide_approval, request_campaign_approval
from app.agents.schemas import CreateCampaignDraftInput, RequestCampaignApprovalInput
from app.agents.service import create_session
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.campaigns import AgentPermission, ApprovalRequest, Campaign, PolicyRule
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem, Payment
from app.models.customers import Customer
from app.models.identity import Merchant, MerchantSettings
from app.models.opportunities import RevenueOpportunity
from app.models.ops import AuditLog, RevenueAttribution
from app.services.merchant_cleanup import reset_merchant

client = TestClient(app)


@pytest.fixture
def full_loop_merchant():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"E2E Loop Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))
    for code, value in {
        "MAX_DISCOUNT_PERCENT": 15, "MAX_CAMPAIGN_BUDGET": 5000, "MAX_DAILY_CAMPAIGNS": 10,
        "MAX_SINGLE_TRANSACTION": 10000, "NO_OUT_OF_STOCK_PRODUCTS": True,
    }.items():
        db.add(PolicyRule(merchant_id=merchant.id, code=code, value_json={"value": value}))
    for code, mode in {"CREATE_CAMPAIGN_DRAFT": "ALLOW", "CREATE_DISCOUNT": "APPROVAL"}.items():
        db.add(AgentPermission(merchant_id=merchant.id, action_code=code, mode=mode))

    source_product = Product(merchant_id=merchant.id, sku="LOOP-SRC", name="Loop Source Product", price_amount=2000, stock_qty=50, stock_status="in_stock")
    target_product = Product(merchant_id=merchant.id, sku="LOOP-TGT", name="Loop Target Product", price_amount=1000, stock_qty=50, stock_status="in_stock")
    db.add_all([source_product, target_product])
    db.flush()

    paying_customer = Customer(merchant_id=merchant.id, name="Loop Test Customer", email="loop.customer@example.com")
    db.add(paying_customer)
    db.flush()
    for i in range(12):
        customer = paying_customer if i == 0 else Customer(merchant_id=merchant.id, name=f"Loop Customer {i}")
        if i != 0:
            db.add(customer)
            db.flush()
        order = Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=2000, total_amount=2000)
        db.add(order)
        db.flush()
        db.add(OrderItem(order_id=order.id, product_id=source_product.id, quantity=1, unit_price_amount=2000))
        if i < 4:
            order2 = Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=1000, total_amount=1000)
            db.add(order2)
            db.flush()
            db.add(OrderItem(order_id=order2.id, product_id=target_product.id, quantity=1, unit_price_amount=1000))

    opportunity = RevenueOpportunity(
        merchant_id=merchant.id, type="cross_sell", source_product_id=source_product.id, target_product_id=target_product.id,
        reach_count=8, confidence=0.4, historical_affinity=2.4, estimated_conversion=0.15,
        estimated_revenue_amount=1200, risk_level="low", priority_score=85,
        evidence_json={"confidence_organic": 0.33, "lift": 2.4}, status="open",
    )
    db.add(opportunity)
    db.commit()

    yield db, merchant.id, source_product.id, target_product.id, opportunity.id
    reset_merchant(db, merchant.id)
    db.close()


def test_full_loop_opportunity_to_attribution(full_loop_merchant):
    db, merchant_id, source_id, target_id, opportunity_id = full_loop_merchant

    # --- STAGE 1: Opportunity -> Agent ---
    session = create_session(db, merchant_id, user_id=None, channel="merchant_console")

    draft = create_campaign_draft(db, merchant_id, session.id, CreateCampaignDraftInput(
        opportunity_id=opportunity_id, name="Full Loop Test Campaign", objective="cross_sell",
        product_ids=[source_id, target_id], discount_percent=10, budget_amount=1000,
    ))
    assert draft.status == "executed", "Stage 1 (draft) failed"
    campaign_id = uuid.UUID(draft.result_json["campaign_id"])

    campaign = db.get(Campaign, campaign_id)
    assert campaign.opportunity_id == opportunity_id, "draft did not link back to the real opportunity"

    opportunity = db.get(RevenueOpportunity, opportunity_id)
    db.refresh(opportunity)
    assert opportunity.status == "actioned", "Stage 1 side effect: opportunity must flip from open to actioned"

    # --- STAGE 2: Agent -> Simulation -> Policy ---
    approval_action = request_campaign_approval(db, merchant_id, session.id, RequestCampaignApprovalInput(campaign_id=campaign_id))
    assert approval_action.status == "pending_approval", "Stage 2 (policy-gated approval request) failed"
    assert approval_action.result_json["simulation"]["expected_revenue"] > 0, "simulation must have run with real, non-zero inputs"

    approval = db.get(ApprovalRequest, approval_action.approval_id)
    assert approval.policy_result_json["passed"] is True, "Stage 2: policy check must have genuinely run and passed"

    db.refresh(campaign)
    assert campaign.status == "pending_approval", "Stage 2 side effect: campaign must reflect pending approval"

    # --- STAGE 3: Approval -> Razorpay ---
    approve_result = decide_approval(db, merchant_id, approval.id, "approve", decided_by_user_id=None)
    assert approve_result["status"] == "approved", "Stage 3 (approval decision) failed"
    assert approve_result["action_status"] == "executed", "Stage 3 (payment link execution) failed"

    db.refresh(campaign)
    assert campaign.status == "running", "Stage 3 side effect: campaign must be running after execution"
    assert float(campaign.expected_revenue_amount) > 0, "Stage 3: expected_revenue_amount must be populated from the frozen simulation"

    payment = db.query(Payment).filter(Payment.campaign_id == campaign_id).one()
    assert payment.status == "created"
    assert payment.provider == "mock"
    assert payment.provider_payment_link_id is not None, "Stage 3: a real (mock) provider payment link ID must exist"

    audit_after_execution = db.query(AuditLog).filter(AuditLog.external_id == str(payment.id), AuditLog.result == "success").one_or_none()
    assert audit_after_execution is not None, "Stage 3 must be audited"

    # --- STAGE 4: Razorpay -> Webhook ---
    settings = get_settings()
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    assert secret, "test requires RAZORPAY_WEBHOOK_SECRET to be configured"

    body = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": payment.provider_payment_link_id, "amount": int(float(payment.amount) * 100),
                    "amount_paid": int(float(payment.amount) * 100), "status": "paid",
                    "customer": {"email": "loop.customer@example.com"},
                }
            },
            "payment": {"entity": {"id": f"pay_e2e_{uuid.uuid4().hex[:12]}", "amount": int(float(payment.amount) * 100), "status": "captured"}},
        },
    }
    raw = json.dumps(body).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    event_id = f"evt_e2e_{uuid.uuid4().hex}"

    webhook_response = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": signature, "x-razorpay-event-id": event_id},
    )
    assert webhook_response.status_code == 200, "Stage 4 (webhook) failed"
    assert webhook_response.json()["status"] == "processed"

    # --- STAGE 5: Webhook -> Attribution ---
    db.expire_all()
    campaign = db.get(Campaign, campaign_id)
    assert campaign.status == "completed", "Stage 5 side effect: campaign must complete on payment confirmation"
    assert float(campaign.actual_revenue_amount) == float(payment.amount), "Stage 5: actual revenue must exactly match what was charged"

    payment = db.get(Payment, payment.id)
    assert payment.status == "paid"
    assert payment.order_id is not None, "Stage 5: a real Order must be created and linked, not left null"

    order = db.get(Order, payment.order_id)
    assert order.status == "paid"
    assert order.source == "merchant_campaign"
    assert order.customer_id is not None

    order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    assert len(order_items) == 2, "the real order must reflect the campaign's actual products, not be empty"

    attribution = db.query(RevenueAttribution).filter(RevenueAttribution.payment_id == payment.id).one()
    assert attribution.attribution_type == "attributed"
    assert attribution.campaign_id == campaign_id
    assert attribution.order_id == order.id
    assert float(attribution.amount) == float(payment.amount)

    # --- FULL-CHAIN INTEGRITY CHECK ---
    full_audit_trail = db.query(AuditLog).filter(
        AuditLog.merchant_id == merchant_id,
        (AuditLog.external_id == str(campaign_id)) | (AuditLog.external_id == str(payment.id)) | (AuditLog.approval_id == approval.id),
    ).order_by(AuditLog.created_at).all()
    actions_seen = [a.action for a in full_audit_trail]
    assert "CREATE_CAMPAIGN_DRAFT" in actions_seen
    assert "CREATE_DISCOUNT" in actions_seen
    assert "CREATE_PAYMENT_LINK" in actions_seen
    assert "PAYMENT_LINK_PAID" in actions_seen
    draft_ts = next(a.created_at for a in full_audit_trail if a.action == "CREATE_CAMPAIGN_DRAFT")
    paid_ts = next(a.created_at for a in full_audit_trail if a.action == "PAYMENT_LINK_PAID")
    assert draft_ts <= paid_ts, "audit trail must be chronologically coherent across the entire loop"
