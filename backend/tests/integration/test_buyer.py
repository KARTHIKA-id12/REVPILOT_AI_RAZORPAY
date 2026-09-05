import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app
from app.models.catalog import Product, ProductCategory, ProductRelation
from app.models.identity import Merchant
from app.services.merchant_cleanup import reset_merchant

client = TestClient(app)


@pytest.fixture
def buyer_catalog():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Buyer Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    category = ProductCategory(merchant_id=merchant.id, name="Gaming")
    db.add(category)
    db.flush()
    keyboard = Product(
        merchant_id=merchant.id, sku="BUYER-KB", name="Test Mechanical Keyboard",
        description="RGB gaming keyboard", price_amount=3499, currency="INR",
        category_id=category.id, stock_qty=10, stock_status="in_stock",
        tags_json=["mechanical", "gaming"], use_cases_json=["gaming", "office"], status="active",
    )
    mouse = Product(
        merchant_id=merchant.id, sku="BUYER-MOUSE", name="Test Wireless Gaming Mouse",
        description="Lightweight gaming mouse", price_amount=1499, currency="INR",
        category_id=category.id, stock_qty=10, stock_status="in_stock",
        tags_json=["wireless", "gaming"], use_cases_json=["gaming"], status="active",
    )
    db.add_all([keyboard, mouse])
    db.flush()
    db.add(ProductRelation(
        product_id=keyboard.id, related_product_id=mouse.id, relation_type="FREQUENTLY_BOUGHT_WITH",
    ))
    db.commit()
    yield db, merchant.id, keyboard.id, mouse.id
    reset_merchant(db, merchant.id)
    db.close()


def test_buyer_query_returns_live_budget_fitting_bundle(buyer_catalog):
    _, merchant_id, keyboard_id, mouse_id = buyer_catalog
    response = client.post("/api/v1/agent/buyer/query", json={
        "merchant_id": str(merchant_id), "query": "I need a gaming setup under ₹5,000",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    bundle = body["bundles"][0]
    assert set(bundle["product_ids"]) == {str(keyboard_id), str(mouse_id)}
    assert bundle["total"]["amount"] == 4998.0


def test_cart_persists_state_and_recomputes_total_from_catalog(buyer_catalog):
    _, merchant_id, keyboard_id, _ = buyer_catalog
    session_ref = f"buyer_{uuid.uuid4().hex}"
    response = client.post("/api/v1/agent/cart", json={
        "merchant_id": str(merchant_id), "session_ref": session_ref,
        "action": "add", "product_id": str(keyboard_id), "quantity": 1,
    })
    assert response.status_code == 200
    assert response.json()["total"]["amount"] == 3499.0

    fetched = client.get("/api/v1/agent/cart", params={"merchant_id": merchant_id, "session_ref": session_ref})
    assert fetched.status_code == 200
    assert fetched.json()["items"][0]["product_id"] == str(keyboard_id)


def test_cart_rejects_budget_exceed_without_mutating(buyer_catalog):
    _, merchant_id, keyboard_id, _ = buyer_catalog
    session_ref = f"buyer_{uuid.uuid4().hex}"
    response = client.post("/api/v1/agent/cart", json={
        "merchant_id": str(merchant_id), "session_ref": session_ref,
        "action": "add", "product_id": str(keyboard_id), "quantity": 1, "max_total": 1000,
    })
    assert response.status_code == 422
    fetched = client.get("/api/v1/agent/cart", params={"merchant_id": merchant_id, "session_ref": session_ref})
    assert fetched.status_code == 200
    assert fetched.json()["items"] == []


def test_compare_rejects_cross_merchant_product(buyer_catalog):
    _, merchant_id, keyboard_id, _ = buyer_catalog
    other_id = uuid.uuid4()
    response = client.get("/api/v1/agent/compare", params={
        "merchant_id": merchant_id, "product_ids": [keyboard_id, other_id],
    })
    assert response.status_code == 404