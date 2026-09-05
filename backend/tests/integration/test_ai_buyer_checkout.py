import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.buyer.service import apply_cart_action, get_or_create_cart
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.catalog import Product
from app.models.commerce import Order, Payment
from app.models.identity import Merchant
from app.services.merchant_cleanup import reset_merchant

client = TestClient(app)


@pytest.fixture
def buyer_cart(monkeypatch):
    monkeypatch.setattr(get_settings(), "DEMO_MODE", True)
    monkeypatch.setattr(get_settings(), "PAYMENT_PROVIDER", "mock")
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Checkout Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    product = Product(
        merchant_id=merchant.id,
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        name="Checkout Product",
        description="A product used by checkout integration tests.",
        price_amount=1250,
        currency="INR",
        stock_qty=4,
        stock_status="in_stock",
        status="active",
    )
    db.add(product)
    db.flush()
    session_ref = f"checkout-test-{uuid.uuid4().hex}"
    cart = get_or_create_cart(db, merchant.id, session_ref)
    apply_cart_action(
        db, merchant.id, session_ref=session_ref, action="add", product_id=product.id, quantity=2,
        customer_id=None, max_total=None,
    )
    db.commit()
    yield db, merchant.id, product.id, cart.id, session_ref
    reset_merchant(db, merchant.id)
    db.close()


def test_checkout_requires_preview_confirmation_and_recomputes_total(buyer_cart):
    db, merchant_id, product_id, cart_id, session_ref = buyer_cart
    preview = client.post("/api/v1/agent/checkout/preview", json={"merchant_id": str(merchant_id), "session_ref": session_ref})
    assert preview.status_code == 200
    assert preview.json()["total"]["amount"] == 2500

    refused = client.post(
        "/api/v1/agent/checkout/confirm",
        json={
            "merchant_id": str(merchant_id), "session_ref": session_ref,
            "preview_id": preview.json()["preview_id"], "confirmed": False,
            "buyer_name": "Buyer", "buyer_email": "buyer@example.com",
        },
    )
    assert refused.status_code == 422
    assert db.query(Order).filter(Order.merchant_id == merchant_id).count() == 0


def test_checkout_demo_payment_is_idempotent_and_settles_inventory(buyer_cart):
    db, merchant_id, product_id, cart_id, session_ref = buyer_cart
    preview = client.post("/api/v1/agent/checkout/preview", json={"merchant_id": str(merchant_id), "session_ref": session_ref}).json()
    confirmed = client.post(
        "/api/v1/agent/checkout/confirm",
        json={
            "merchant_id": str(merchant_id), "session_ref": session_ref,
            "preview_id": preview["preview_id"], "confirmed": True,
            "buyer_name": "Buyer", "buyer_email": "buyer@example.com",
        },
    )
    assert confirmed.status_code == 200
    payload = confirmed.json()
    paid = client.post(
        "/api/v1/agent/checkout/verify",
        json={"merchant_id": str(merchant_id), "order_id": payload["order_id"], "demo": True},
    )
    assert paid.status_code == 200
    assert paid.json()["payment_status"] == "paid"

    duplicate = client.post(
        "/api/v1/agent/checkout/verify",
        json={"merchant_id": str(merchant_id), "order_id": payload["order_id"], "demo": True},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    db.expire_all()
    assert db.get(Product, product_id).stock_qty == 2
    assert db.query(Payment).filter(Payment.merchant_id == merchant_id, Payment.status == "paid").count() == 1