"""These are the load-bearing tests for the entire product's safety story.
Each one is directly lifted from the spec's 'Critical Safety Test' /
'Duplicate Webhook Test' / 'Duplicate Action Test' / 'Out-of-Stock Test' /
'Budget Test' / 'AI Hallucination Test' sections. If any of these fail,
the product's core promise — 'AI never has unrestricted access to money' —
is broken, regardless of how good anything else looks."""

import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.agents.pipeline import create_campaign_draft, decide_approval, request_campaign_approval
from app.agents.schemas import CreateCampaignDraftInput, RequestCampaignApprovalInput
from app.agents.service import create_session, handle_message
from app.db.session import SessionLocal
from app.models.campaigns import AgentPermission, ApprovalRequest, Campaign, PolicyRule
from app.models.catalog import Product
from app.models.commerce import Payment
from app.models.identity import Merchant, MerchantSettings


@pytest.fixture
def merchant_with_products():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Safety Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))

    for code, value in {
        "MAX_DISCOUNT_PERCENT": 15, "MAX_CAMPAIGN_BUDGET": 5000, "MAX_DAILY_CAMPAIGNS": 10,
        "MAX_SINGLE_TRANSACTION": 10000, "NO_OUT_OF_STOCK_PRODUCTS": True,
    }.items():
        db.add(PolicyRule(merchant_id=merchant.id, code=code, value_json={"value": value}))

    for code, mode in {
        "CREATE_CAMPAIGN_DRAFT": "ALLOW", "CREATE_DISCOUNT": "APPROVAL", "CREATE_PAYMENT_LINK": "APPROVAL",
    }.items():
        db.add(AgentPermission(merchant_id=merchant.id, action_code=code, mode=mode))

    product_a = Product(merchant_id=merchant.id, sku="SAFE-A", name="Product A", price_amount=1000, stock_qty=50, stock_status="in_stock")
    product_b = Product(merchant_id=merchant.id, sku="SAFE-B", name="Product B", price_amount=500, stock_qty=50, stock_status="in_stock")
    oos_product = Product(merchant_id=merchant.id, sku="SAFE-OOS", name="Sold Out Product", price_amount=800, stock_qty=0, stock_status="out_of_stock")
    db.add_all([product_a, product_b, oos_product])
    db.flush()

    # A little real order history so simulations against this merchant
    # aren't trivially zero (reach=0) — makes tests that check
    # expected_revenue_amount propagation meaningful rather than a
    # degenerate edge case.
    from app.models.commerce import Order as _Order
    from app.models.commerce import OrderItem as _OrderItem
    from app.models.customers import Customer as _Customer

    for i in range(10):
        customer = _Customer(merchant_id=merchant.id, name=f"Safety Test Customer {i}")
        db.add(customer)
        db.flush()
        order = _Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=1000, total_amount=1000)
        db.add(order)
        db.flush()
        db.add(_OrderItem(order_id=order.id, product_id=product_a.id, quantity=1, unit_price_amount=1000))
        if i < 3:  # a few also bought product B, giving organic_confidence a real non-zero value
            order_b = _Order(merchant_id=merchant.id, customer_id=customer.id, status="paid", subtotal_amount=500, total_amount=500)
            db.add(order_b)
            db.flush()
            db.add(_OrderItem(order_id=order_b.id, product_id=product_b.id, quantity=1, unit_price_amount=500))
    db.flush()

    session = create_session(db, merchant.id, user_id=None)

    yield db, merchant.id, session.id, product_a.id, product_b.id, oos_product.id
    # Several tests above call Action Pipeline functions that db.commit()
    # internally, so db.rollback() here is a no-op for anything already
    # committed — the fixture must explicitly delete what it created,
    # or it silently leaks a permanent orphaned merchant on every run.
    from app.services.merchant_cleanup import reset_merchant
    reset_merchant(db, merchant.id)
    db.close()


# --- Spec §100: Critical safety test (20% blocked, 10% requires approval, then executes) ---

def test_discount_over_cap_is_blocked(merchant_with_products):
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        name="Test Campaign", objective="cross_sell", product_ids=[product_a, product_b],
        discount_percent=20, budget_amount=1000,
    ))
    assert draft.status == "executed"  # draft creation itself only checks stock/budget, not discount cap

    approval_action = request_campaign_approval(db, merchant_id, session_id, RequestCampaignApprovalInput(
        campaign_id=uuid.UUID(draft.result_json["campaign_id"]),
    ))
    assert approval_action.status == "blocked"
    assert "20" in approval_action.error and "15" in approval_action.error

    campaign = db.get(Campaign, uuid.UUID(draft.result_json["campaign_id"]))
    assert campaign.status == "draft"  # never advanced past draft — no approval request was created
    assert db.query(ApprovalRequest).filter(ApprovalRequest.campaign_id == campaign.id).count() == 0


def test_discount_within_cap_requires_approval_then_executes_on_approval(merchant_with_products):
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        name="Test Campaign", objective="cross_sell", product_ids=[product_a, product_b],
        discount_percent=10, budget_amount=1000,
    ))
    campaign_id = uuid.UUID(draft.result_json["campaign_id"])

    approval_action = request_campaign_approval(db, merchant_id, session_id, RequestCampaignApprovalInput(campaign_id=campaign_id))
    assert approval_action.status == "pending_approval"

    campaign = db.get(Campaign, campaign_id)
    assert campaign.status == "pending_approval"

    approval_id = approval_action.approval_id
    result = decide_approval(db, merchant_id, approval_id, "approve", decided_by_user_id=None)
    assert result["status"] == "approved"
    assert result["action_status"] == "executed"

    db.refresh(campaign)
    assert campaign.status == "running"
    assert campaign.starts_at is not None
    # Regression: expected_revenue_amount must be populated from the frozen
    # simulation, not left at its 0 default — this was a real gap found
    # while building the Campaigns detail view (spec explicitly calls for
    # showing expected revenue, and it silently showed ₹0 for every
    # campaign until this was fixed). The fixture now has real order
    # history so this is a genuine positive-value assertion, not a
    # degenerate zero-reach edge case.
    assert float(campaign.expected_revenue_amount) > 0
    payment = db.query(Payment).filter(Payment.campaign_id == campaign.id).one()
    assert payment.status == "created"
    assert payment.provider == "mock"  # DEMO_MODE, no real Razorpay creds in this test


# --- Spec §102: Duplicate action / idempotency test ---

def test_double_approving_same_request_does_not_double_charge(merchant_with_products):
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        name="Idempotency Test", objective="cross_sell", product_ids=[product_a, product_b],
        discount_percent=10, budget_amount=1000,
    ))
    campaign_id = uuid.UUID(draft.result_json["campaign_id"])
    approval_action = request_campaign_approval(db, merchant_id, session_id, RequestCampaignApprovalInput(campaign_id=campaign_id))
    approval_id = approval_action.approval_id

    first = decide_approval(db, merchant_id, approval_id, "approve", decided_by_user_id=None)
    assert first["status"] == "approved"

    # Second attempt: approval is already 'approved', not 'pending' — the
    # decide_approval guard itself refuses to act on a non-pending request.
    second = decide_approval(db, merchant_id, approval_id, "approve", decided_by_user_id=None)
    assert "error" in second

    payments = db.query(Payment).filter(Payment.campaign_id == campaign_id).all()
    assert len(payments) == 1  # exactly one payment, never two


def test_idempotency_key_prevents_duplicate_even_if_guard_were_bypassed(merchant_with_products):
    """Defense in depth: even if something called _execute_payment_link
    twice with the same idempotency_key directly (bypassing the pending-
    status guard), the payment-level idempotency check must still catch it."""
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products
    from app.agents.pipeline import _execute_payment_link

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        name="Direct Idempotency Test", objective="cross_sell", product_ids=[product_a, product_b],
        discount_percent=10, budget_amount=1000,
    ))
    campaign = db.get(Campaign, uuid.UUID(draft.result_json["campaign_id"]))
    frozen_payload = {
        "product_ids": [str(product_a), str(product_b)], "discount_percent": 10.0, "budget_amount": 1000.0,
        "simulation": {"expected_revenue": 5000.0},
    }

    action1 = _execute_payment_link(db, merchant_id, session_id, campaign, frozen_payload, approval_id=None, idempotency_key="fixed_key_123")
    action2 = _execute_payment_link(db, merchant_id, session_id, campaign, frozen_payload, approval_id=None, idempotency_key="fixed_key_123")

    assert action1.result_json.get("payment_id") == action2.result_json.get("payment_id")
    assert action2.result_json.get("duplicate_prevented") is True
    assert db.query(Payment).filter(Payment.idempotency_key == "fixed_key_123").count() == 1


# --- Spec §103: Out-of-stock test ---

def test_out_of_stock_product_blocks_campaign_draft(merchant_with_products):
    db, merchant_id, session_id, product_a, _, oos_product = merchant_with_products

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        name="OOS Test", objective="cross_sell", product_ids=[product_a, oos_product],
        discount_percent=10, budget_amount=1000,
    ))
    assert draft.status == "blocked"
    assert "Sold Out Product" in draft.error


# --- Spec §104: Budget test ---

def test_budget_exceeding_policy_blocks_approval(merchant_with_products):
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        name="Budget Test", objective="cross_sell", product_ids=[product_a, product_b],
        discount_percent=10, budget_amount=1000,  # passes draft-time check
    ))
    campaign = db.get(Campaign, uuid.UUID(draft.result_json["campaign_id"]))
    campaign.budget_amount = 9000  # simulate a later edit that exceeds MAX_CAMPAIGN_BUDGET=5000
    db.flush()

    approval_action = request_campaign_approval(db, merchant_id, session_id, RequestCampaignApprovalInput(campaign_id=campaign.id))
    assert approval_action.status == "blocked"
    assert "9,000" in approval_action.error or "9000" in approval_action.error


# --- Spec §105: AI hallucination test ---

def test_asking_about_nonexistent_product_never_invents_a_price(merchant_with_products):
    db, merchant_id, session_id, _, _, _ = merchant_with_products
    from app.models.agent import AgentSession

    session = db.get(AgentSession, session_id)
    result = handle_message(db, session, merchant_id, "What is the price of the Quantum Flux Capacitor?")
    assert "couldn't find" in result["reply"].lower()
    assert "quantum" not in result["reply"].lower()  # never echoes back a fabricated match


def test_create_campaign_phrase_containing_opportunity_word_still_routes_to_create(merchant_with_products):
    """Regression test for a real routing bug found during development:
    'Create a campaign for this opportunity' contains the substring
    'opportunit', which a naive keyword check matched before the
    'create'+'campaign' branch, silently routing to a read-only lookup
    instead of actually creating anything."""
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products
    from app.models.agent import AgentSession
    from app.models.opportunities import RevenueOpportunity

    db.add(RevenueOpportunity(
        merchant_id=merchant_id, type="cross_sell", source_product_id=product_a, target_product_id=product_b,
        reach_count=10, confidence=0.5, historical_affinity=2.0, estimated_conversion=0.2,
        estimated_revenue_amount=5000, risk_level="low", priority_score=90, evidence_json={}, status="open",
    ))
    db.flush()

    session = db.get(AgentSession, session_id)
    result = handle_message(db, session, merchant_id, "Create a campaign for this opportunity")
    assert result["intent"] == "CREATE_CAMPAIGN_DRAFT"
    assert "draft_action_id" in result


def test_refresh_analytics_never_breaks_on_opportunity_referenced_by_campaign(merchant_with_products):
    """Regression test for a real cross-phase bug found during
    development: acting on an opportunity (creating a campaign from it)
    didn't mark the opportunity 'actioned', so re-running the analytics
    refresh (which deletes stale 'open' opportunities) hit a foreign-key
    violation on any opportunity a campaign now pointed to — crashing the
    entire analytics pipeline, not just skipping one row."""
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products
    from app.models.opportunities import RevenueOpportunity
    from app.opportunities.service import run_full_analytics

    opportunity = RevenueOpportunity(
        merchant_id=merchant_id, type="cross_sell", source_product_id=product_a, target_product_id=product_b,
        reach_count=10, confidence=0.5, historical_affinity=2.0, estimated_conversion=0.2,
        estimated_revenue_amount=5000, risk_level="low", priority_score=90, evidence_json={}, status="open",
    )
    db.add(opportunity)
    db.flush()

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        opportunity_id=opportunity.id, name="From Opportunity", objective="cross_sell",
        product_ids=[product_a, product_b], discount_percent=10, budget_amount=1000,
    ))
    assert draft.status == "executed"

    db.refresh(opportunity)
    assert opportunity.status == "actioned"  # no longer 'open' — the fix

    # This must not raise IntegrityError even though a campaign still
    # references this opportunity.
    summary = run_full_analytics(db, merchant_id)
    assert summary["opportunities_detected"] >= 0

    still_exists = db.get(RevenueOpportunity, opportunity.id)
    assert still_exists is not None  # preserved, not deleted, because it's actioned


# --- Permission DENY test ---

def test_duplicate_permission_row_rejected_by_db_constraint(merchant_with_products):
    """This is a regression test for a real bug found during development:
    before a unique constraint existed on (merchant_id, action_code),
    inserting two AgentPermission rows for the same action silently broke
    get_permission_mode's one_or_none() lookup with an unhandled
    MultipleResultsFound — a genuine loophole where a data-integrity bug
    could crash the permission gate instead of failing closed. The DB now
    refuses the duplicate outright."""
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products
    from sqlalchemy.exc import IntegrityError

    db.add(AgentPermission(merchant_id=merchant_id, action_code="CREATE_CAMPAIGN_DRAFT", mode="DENY"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_denied_permission_blocks_regardless_of_policy_passing(merchant_with_products):
    db, merchant_id, session_id, product_a, product_b, _ = merchant_with_products
    # Simulate the merchant changing an existing permission (real-world
    # path: UPDATE the row, never INSERT a second one for the same
    # merchant+action_code — the DB now enforces this with a unique
    # constraint, so a duplicate insert would raise IntegrityError).
    existing = db.query(AgentPermission).filter(
        AgentPermission.merchant_id == merchant_id, AgentPermission.action_code == "CREATE_CAMPAIGN_DRAFT"
    ).one()
    existing.mode = "DENY"
    db.flush()

    draft = create_campaign_draft(db, merchant_id, session_id, CreateCampaignDraftInput(
        name="Denied Test", objective="cross_sell", product_ids=[product_a, product_b],
        discount_percent=5, budget_amount=500,  # would otherwise pass every policy check
    ))
    assert draft.status == "blocked"
    assert db.query(Campaign).filter(Campaign.name == "Denied Test").count() == 0  # nothing was created
