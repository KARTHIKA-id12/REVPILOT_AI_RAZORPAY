import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.campaigns import PolicyRule
from app.models.identity import Merchant
from app.policies.rules import (
    check_campaign_budget,
    check_discount_percent,
    check_stock_availability,
    run_campaign_policy_checks,
)


@pytest.fixture
def db_with_merchant():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Policy Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(PolicyRule(merchant_id=merchant.id, code="MAX_DISCOUNT_PERCENT", value_json={"value": 15}))
    db.add(PolicyRule(merchant_id=merchant.id, code="MAX_CAMPAIGN_BUDGET", value_json={"value": 5000}))
    db.flush()
    yield db, merchant.id
    db.rollback()
    db.close()


def test_discount_within_cap_passes(db_with_merchant):
    db, merchant_id = db_with_merchant
    result = check_discount_percent(db, merchant_id, 10)
    assert result.passed is True
    assert result.violations == []


def test_discount_exceeding_cap_fails_with_clear_reason(db_with_merchant):
    db, merchant_id = db_with_merchant
    result = check_discount_percent(db, merchant_id, 20)
    assert result.passed is False
    assert "20" in result.violations[0]
    assert "15" in result.violations[0]


def test_negative_discount_rejected(db_with_merchant):
    db, merchant_id = db_with_merchant
    result = check_discount_percent(db, merchant_id, -5)
    assert result.passed is False


def test_missing_policy_row_uses_safe_default(db_with_merchant):
    """A merchant with no MAX_SINGLE_TRANSACTION row configured must still
    be protected by the documented spec default, not silently unlimited."""
    db, merchant_id = db_with_merchant
    from app.policies.rules import check_single_transaction

    result = check_single_transaction(db, merchant_id, 50000)  # far above the 10,000 spec default
    assert result.passed is False


def test_budget_check(db_with_merchant):
    db, merchant_id = db_with_merchant
    assert check_campaign_budget(db, merchant_id, 3000).passed is True
    assert check_campaign_budget(db, merchant_id, 7000).passed is False


def test_combined_check_reports_all_violations_not_just_first(db_with_merchant):
    db, merchant_id = db_with_merchant
    result = run_campaign_policy_checks(
        db, merchant_id, discount_percent=25, budget_amount=9000, product_ids=[], campaigns_created_today=0,
    )
    assert result.passed is False
    assert len(result.violations) == 2  # both discount AND budget violated


def test_out_of_stock_product_blocks_action(db_with_merchant):
    db, merchant_id = db_with_merchant
    from app.models.catalog import Product

    oos_product = Product(
        merchant_id=merchant_id, sku="OOS-1", name="Sold Out Thing", price_amount=100,
        stock_qty=0, stock_status="out_of_stock",
    )
    db.add(oos_product)
    db.flush()

    result = check_stock_availability(db, merchant_id, [oos_product.id])
    assert result.passed is False
    assert "Sold Out Thing" in result.violations[0]


def test_in_stock_products_pass(db_with_merchant):
    db, merchant_id = db_with_merchant
    from app.models.catalog import Product

    product = Product(merchant_id=merchant_id, sku="OK-1", name="Available Thing", price_amount=100, stock_qty=10, stock_status="in_stock")
    db.add(product)
    db.flush()
    assert check_stock_availability(db, merchant_id, [product.id]).passed is True
