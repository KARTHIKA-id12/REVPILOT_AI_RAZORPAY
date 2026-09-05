"""Regression test for a real bug found during Phase 7 development:
the demo reset logic predated campaigns, approval requests, agent
sessions/actions, and customer segments — so resetting the demo after any
real usage (an agent chat, an approved campaign) crashed with a foreign
key violation instead of cleanly restoring the deterministic demo state.
This exercises the actual reset function against a merchant that has one
of everything, the way real usage leaves data behind.

The reset logic itself now lives in app/services/merchant_cleanup.py,
shared by scripts/seed_demo.py AND this test's own teardown — using it
here for cleanup is itself part of what's being tested, and it's also
what stops this test from permanently leaking a throwaway merchant into
the shared database (a real hygiene bug found while auditing Phase 10:
several tests call pipeline functions that commit() internally, so a
plain db.rollback() in teardown was a no-op).
"""

import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.agents.pipeline import create_campaign_draft, request_campaign_approval
from app.agents.schemas import CreateCampaignDraftInput, RequestCampaignApprovalInput
from app.agents.service import create_session, handle_message
from app.db.session import SessionLocal
from app.models.campaigns import AgentPermission, PolicyRule
from app.models.catalog import Product
from app.models.identity import Merchant, MerchantSettings
from app.opportunities.service import run_full_analytics
from app.services.merchant_cleanup import reset_merchant


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        session.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        session.close()
        pytest.skip("Postgres not reachable in this environment")
    yield session
    session.close()


def test_reset_merchant_handles_full_cross_phase_data(db):
    merchant = Merchant(name=f"Reset Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))
    for code, value in {"MAX_DISCOUNT_PERCENT": 15, "MAX_CAMPAIGN_BUDGET": 5000, "NO_OUT_OF_STOCK_PRODUCTS": True}.items():
        db.add(PolicyRule(merchant_id=merchant.id, code=code, value_json={"value": value}))
    for code, mode in {"CREATE_CAMPAIGN_DRAFT": "ALLOW", "CREATE_DISCOUNT": "APPROVAL"}.items():
        db.add(AgentPermission(merchant_id=merchant.id, action_code=code, mode=mode))

    product_a = Product(merchant_id=merchant.id, sku="RESET-A", name="Reset A", price_amount=1000, stock_qty=50, stock_status="in_stock")
    product_b = Product(merchant_id=merchant.id, sku="RESET-B", name="Reset B", price_amount=500, stock_qty=50, stock_status="in_stock")
    db.add_all([product_a, product_b])
    db.flush()

    # Leave behind exactly the kind of cross-phase state real usage creates:
    # an agent session, RFM segment memberships (via full analytics run),
    # a campaign, and a pending approval request.
    session = create_session(db, merchant.id, user_id=None)
    handle_message(db, session, merchant.id, "What is my revenue?")

    run_full_analytics(db, merchant.id)  # creates customer_segments rows even with zero customers

    draft = create_campaign_draft(db, merchant.id, session.id, CreateCampaignDraftInput(
        name="Reset Test Campaign", objective="cross_sell", product_ids=[product_a.id, product_b.id],
        discount_percent=10, budget_amount=1000,
    ))
    request_campaign_approval(db, merchant.id, session.id, RequestCampaignApprovalInput(
        campaign_id=uuid.UUID(draft.result_json["campaign_id"]),
    ))

    # This must not raise — that's the entire point of the test. It also
    # cleans up after itself, so this test leaves nothing behind.
    reset_merchant(db, merchant.id)

    assert db.get(Merchant, merchant.id) is None
