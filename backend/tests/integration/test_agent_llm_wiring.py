"""Proves the LLM-wiring closes the gap flagged during audit: with a real
provider configured, `handle_message` now calls `get_ai_provider()` and
routes its (validated) structured output through the exact same tool
dispatch and Action Pipeline the keyword router already used -- not a
parallel/duplicated code path. A fake provider stands in for the real
Hugging Face call so this is deterministic and network-free; the HTTP
call itself lives entirely in app/agents/huggingface_provider.py, which
this suite does not need to exercise to prove the wiring is correct.

Also proves the resilience contract: a provider that returns garbage, or
raises, must never crash the chat -- it should log a failed
`llm_intent_classify` tool call and fall back to the keyword router.
"""
import json
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.agents.service import create_session, handle_message
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.agent import AgentToolCall
from app.models.campaigns import AgentPermission, Campaign, PolicyRule
from app.models.catalog import Product
from app.models.customers import Customer
from app.models.identity import Merchant, MerchantSettings
from app.models.opportunities import RevenueOpportunity
from app.services.merchant_cleanup import reset_merchant


class _FakeProvider:
    """Stands in for HuggingFaceProvider -- same .complete() interface,
    no network call."""

    def __init__(self, response_text: str | None = None, raise_exc: Exception | None = None):
        self._response_text = response_text
        self._raise_exc = raise_exc

    def complete(self, *, system: str, messages: list[dict], response_schema: dict | None = None) -> str:
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response_text


@pytest.fixture
def llm_agent_merchant(monkeypatch):
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    monkeypatch.setattr(get_settings(), "AI_PROVIDER", "huggingface")
    monkeypatch.setattr(get_settings(), "AI_API_KEY", "fake-test-token")

    merchant = Merchant(name=f"LLM Wiring Test {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))

    source = Product(merchant_id=merchant.id, sku="LLM-A", name="Source Product", price_amount=1000, stock_qty=50, stock_status="in_stock")
    target = Product(merchant_id=merchant.id, sku="LLM-B", name="Target Product", price_amount=500, stock_qty=50, stock_status="in_stock")
    db.add_all([source, target])
    db.flush()

    for i in range(3):
        db.add(Customer(merchant_id=merchant.id, name=f"Cust {i}", email=f"llmcust{i}@example.com"))

    opp = RevenueOpportunity(
        merchant_id=merchant.id, type="cross_sell", source_product_id=source.id, target_product_id=target.id,
        reach_count=3, confidence=0.4, historical_affinity=2.0, estimated_conversion=0.2,
        estimated_revenue_amount=5000, risk_level="low", priority_score=80, status="open",
        evidence_json={"note": "seeded for llm wiring test"},
    )
    db.add(opp)
    db.add(PolicyRule(merchant_id=merchant.id, code="MAX_DISCOUNT_PERCENT", value_json={"value": 15}))
    db.add(PolicyRule(merchant_id=merchant.id, code="MAX_CAMPAIGN_BUDGET", value_json={"value": 5000}))
    db.add(PolicyRule(merchant_id=merchant.id, code="MAX_DAILY_CAMPAIGNS", value_json={"value": 10}))
    db.add(PolicyRule(merchant_id=merchant.id, code="NO_OUT_OF_STOCK_PRODUCTS", value_json={"value": True}))
    db.add(AgentPermission(merchant_id=merchant.id, action_code="CREATE_CAMPAIGN_DRAFT", mode="ALLOW"))
    db.add(AgentPermission(merchant_id=merchant.id, action_code="CREATE_DISCOUNT", mode="APPROVAL"))
    db.commit()

    yield db, merchant.id

    db.query(Campaign).filter(Campaign.merchant_id == merchant.id).delete()
    reset_merchant(db, merchant.id)
    db.close()


def test_llm_provider_output_drives_the_real_action_pipeline(llm_agent_merchant, monkeypatch):
    db, merchant_id = llm_agent_merchant
    monkeypatch.setattr(
        "app.agents.providers.get_ai_provider",
        lambda: _FakeProvider(json.dumps({"intent": "SIMULATE_CAMPAIGN", "discount_percent": 12})),
    )

    session = create_session(db, merchant_id, user_id=None)
    result = handle_message(db, session, merchant_id, "hey, run the numbers on a discount for me")

    assert result["intent"] == "SIMULATE_CAMPAIGN"
    assert result["tool_result"] is not None
    # The simulation math is the real deterministic engine -- discount 12%
    # against a real seeded opportunity, not anything the fake provider computed.
    assert "expected_revenue" in result["tool_result"]

    logged_calls = db.query(AgentToolCall).filter(AgentToolCall.session_id == session.id, AgentToolCall.tool_name == "llm_intent_classify").all()
    assert len(logged_calls) == 1
    assert logged_calls[0].status == "ok"


def test_llm_provider_still_respects_policy_cap_on_create_campaign(llm_agent_merchant, monkeypatch):
    """The LLM proposing a 40% discount must be blocked by the same 15%
    policy cap the keyword router is bound by -- proving the provider
    swap changes intent *extraction* only, never enforcement."""
    db, merchant_id = llm_agent_merchant
    monkeypatch.setattr(
        "app.agents.providers.get_ai_provider",
        lambda: _FakeProvider(json.dumps({"intent": "CREATE_CAMPAIGN_DRAFT", "discount_percent": 40})),
    )

    session = create_session(db, merchant_id, user_id=None)
    result = handle_message(db, session, merchant_id, "please create a big discount campaign")

    assert result["intent"] == "CREATE_CAMPAIGN_DRAFT"
    assert "blocked" in result["reply"].lower()
    # The draft record keeps the originally-proposed 40% for audit
    # evidence, but the campaign must never be allowed to advance past
    # "draft" -- proving the 15% policy cap applies identically whether
    # the discount came from the keyword router or the LLM.
    campaign = db.query(Campaign).filter(Campaign.merchant_id == merchant_id).order_by(Campaign.created_at.desc()).first()
    assert campaign is not None
    assert campaign.discount_percent == 40
    assert campaign.status == "draft", "a policy-violating discount must never advance a campaign past draft status"


def test_malformed_llm_json_falls_back_to_keyword_router_not_a_crash(llm_agent_merchant, monkeypatch):
    db, merchant_id = llm_agent_merchant
    monkeypatch.setattr("app.agents.providers.get_ai_provider", lambda: _FakeProvider("not json at all"))

    session = create_session(db, merchant_id, user_id=None)
    result = handle_message(db, session, merchant_id, "what's my top opportunity?")

    # Falls back to the keyword router, which correctly matches "opportunit" in the text.
    assert result["intent"] == "VIEW_OPPORTUNITIES"
    failed_calls = db.query(AgentToolCall).filter(AgentToolCall.session_id == session.id, AgentToolCall.tool_name == "llm_intent_classify", AgentToolCall.status == "error").all()
    assert len(failed_calls) == 1


def test_llm_intent_outside_closed_set_is_rejected_not_trusted(llm_agent_merchant, monkeypatch):
    """A model hallucinating an intent name outside the fixed enum (e.g.
    trying REFUND_PAYMENT, which isn't even a chat intent) must fail
    Pydantic validation and fall back, never silently execute."""
    db, merchant_id = llm_agent_merchant
    monkeypatch.setattr(
        "app.agents.providers.get_ai_provider",
        lambda: _FakeProvider(json.dumps({"intent": "REFUND_PAYMENT", "discount_percent": 5})),
    )

    session = create_session(db, merchant_id, user_id=None)
    result = handle_message(db, session, merchant_id, "how much revenue have we made?")

    assert result["intent"] == "VIEW_REVENUE"  # keyword fallback, not the hallucinated intent
    failed_calls = db.query(AgentToolCall).filter(AgentToolCall.session_id == session.id, AgentToolCall.tool_name == "llm_intent_classify", AgentToolCall.status == "error").all()
    assert len(failed_calls) == 1


def test_provider_network_exception_falls_back_gracefully(llm_agent_merchant, monkeypatch):
    from app.core.errors import AppError

    db, merchant_id = llm_agent_merchant
    monkeypatch.setattr(
        "app.agents.providers.get_ai_provider",
        lambda: _FakeProvider(raise_exc=AppError("AI_PROVIDER_TIMEOUT", "timed out", status_code=504)),
    )

    session = create_session(db, merchant_id, user_id=None)
    result = handle_message(db, session, merchant_id, "show me my customer segments please")

    assert result["intent"] == "VIEW_SEGMENTS"
    failed_calls = db.query(AgentToolCall).filter(AgentToolCall.session_id == session.id, AgentToolCall.tool_name == "llm_intent_classify", AgentToolCall.status == "error").all()
    assert len(failed_calls) == 1
