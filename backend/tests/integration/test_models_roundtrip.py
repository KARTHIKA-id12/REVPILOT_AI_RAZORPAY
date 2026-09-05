"""Integration test proving the ORM models round-trip against Postgres.
Requires DATABASE_URL to point at a reachable Postgres with migrations
applied (see README quickstart). Skips gracefully if unreachable, so
`pytest` still passes in environments without a DB (e.g. a bare unit-test
CI stage) — but when the DB *is* up, this is a real, non-mocked check."""

import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.catalog import Product, ProductCategory
from app.models.identity import Merchant


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        session.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        pytest.skip("Postgres not reachable in this environment")
    yield session
    session.rollback()
    session.close()


def test_merchant_and_product_roundtrip(db):
    merchant = Merchant(name=f"Test Merchant {uuid.uuid4().hex[:6]}", category="Electronics", status="active")
    db.add(merchant)
    db.flush()

    category = ProductCategory(merchant_id=merchant.id, name="Gaming Accessories")
    db.add(category)
    db.flush()

    product = Product(
        merchant_id=merchant.id,
        sku=f"TN-TEST-{uuid.uuid4().hex[:6]}",
        name="Test Mechanical Keyboard",
        price_amount=3499,
        category_id=category.id,
        stock_qty=50,
    )
    db.add(product)
    db.flush()

    fetched = db.get(Product, product.id)
    assert fetched is not None
    assert fetched.name == "Test Mechanical Keyboard"
    assert fetched.merchant_id == merchant.id

    db.rollback()  # leave no test data behind
