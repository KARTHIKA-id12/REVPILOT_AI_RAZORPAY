"""Proves the AI Buyer LLM wiring closes the same gap as the merchant
Agent's: with a real provider configured, buyer_query() calls
get_ai_provider() to extract budget/search terms, but ranking, pricing,
and availability are still 100% the real deterministic catalog match —
the fake provider here never invents a product or a price.
"""
import json
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.buyer.service import buyer_query
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.catalog import Product
from app.models.identity import Merchant
from app.services.merchant_cleanup import reset_merchant


class _FakeProvider:
    def __init__(self, response_text: str | None = None, raise_exc: Exception | None = None):
        self._response_text = response_text
        self._raise_exc = raise_exc

    def complete(self, *, system: str, messages: list[dict], response_schema: dict | None = None) -> str:
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response_text


@pytest.fixture
def buyer_llm_merchant(monkeypatch):
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    monkeypatch.setattr(get_settings(), "AI_PROVIDER", "huggingface")
    monkeypatch.setattr(get_settings(), "AI_API_KEY", "fake-test-token")

    merchant = Merchant(name=f"Buyer LLM Test {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    keyboard = Product(
        merchant_id=merchant.id, sku="BLLM-KB", name="Mechanical Keyboard",
        description="A mechanical keyboard for gaming.", price_amount=3499, currency="INR",
        stock_qty=20, stock_status="in_stock", status="active",
    )
    mouse = Product(
        merchant_id=merchant.id, sku="BLLM-MS", name="Wireless Gaming Mouse",
        description="A wireless mouse for gaming.", price_amount=1499, currency="INR",
        stock_qty=20, stock_status="in_stock", status="active",
    )
    db.add_all([keyboard, mouse])
    db.commit()

    yield db, merchant.id, keyboard.id, mouse.id

    reset_merchant(db, merchant.id)
    db.close()


def test_llm_extracted_terms_widen_matching_against_real_catalog(buyer_llm_merchant, monkeypatch):
    """The buyer's raw text doesn't mention 'keyboard' or 'mouse'
    directly -- only the fake LLM's extracted terms do. If ranking still
    surfaces the right real products, the LLM's output is genuinely
    driving the real deterministic ranker, not being ignored."""
    db, merchant_id, keyboard_id, mouse_id = buyer_llm_merchant
    monkeypatch.setattr(
        "app.agents.providers.get_ai_provider",
        lambda: _FakeProvider(json.dumps({"max_budget": 5000, "search_terms": ["keyboard", "mouse", "gaming"]})),
    )

    result = buyer_query(db, merchant_id, "I need a good desk setup for playing games at night")

    assert result["intent_source"] == "llm"
    returned_ids = {p["id"] for p in result["products"]}
    assert str(keyboard_id) in returned_ids
    assert str(mouse_id) in returned_ids
    # Budget is still the real number from the fake provider, but every
    # price shown comes from the real Product rows, not the provider.
    assert all(p["price"]["amount"] <= 5000 for p in result["products"])


def test_explicit_budget_argument_always_wins_over_llm_extraction(buyer_llm_merchant, monkeypatch):
    db, merchant_id, _keyboard_id, mouse_id = buyer_llm_merchant
    monkeypatch.setattr(
        "app.agents.providers.get_ai_provider",
        lambda: _FakeProvider(json.dumps({"max_budget": 50000, "search_terms": ["mouse"]})),
    )

    # Caller explicitly passed max_budget=1500 -- this must not be
    # overridden by the fake provider's (much larger) 50000 guess.
    result = buyer_query(db, merchant_id, "just a mouse please", max_budget=1500)

    returned_ids = {p["id"] for p in result["products"]}
    assert str(mouse_id) in returned_ids
    assert all(p["price"]["amount"] <= 1500 for p in result["products"])


def test_malformed_llm_response_falls_back_to_keyword_extraction(buyer_llm_merchant, monkeypatch):
    db, merchant_id, keyboard_id, _mouse_id = buyer_llm_merchant
    monkeypatch.setattr("app.agents.providers.get_ai_provider", lambda: _FakeProvider("this is not json"))

    result = buyer_query(db, merchant_id, "show me a keyboard")

    assert result["intent_source"] == "keyword"
    returned_ids = {p["id"] for p in result["products"]}
    assert str(keyboard_id) in returned_ids


def test_provider_exception_falls_back_gracefully_not_a_crash(buyer_llm_merchant, monkeypatch):
    db, merchant_id, keyboard_id, _mouse_id = buyer_llm_merchant
    monkeypatch.setattr(
        "app.agents.providers.get_ai_provider",
        lambda: _FakeProvider(raise_exc=AppError("AI_PROVIDER_ERROR", "boom", status_code=502)),
    )

    result = buyer_query(db, merchant_id, "show me a keyboard")

    assert result["intent_source"] == "keyword"
    returned_ids = {p["id"] for p in result["products"]}
    assert str(keyboard_id) in returned_ids
