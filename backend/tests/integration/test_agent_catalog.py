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
def merchant_with_catalog():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Catalog Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()

    category = ProductCategory(merchant_id=merchant.id, name="Test Gadgets")
    db.add(category)
    db.flush()

    keyboard = Product(
        merchant_id=merchant.id, sku="CAT-KB", name="Test Keyboard", description="A mechanical keyboard for gaming",
        price_amount=3000, currency="INR", category_id=category.id, stock_qty=10, stock_status="in_stock",
        use_cases_json=["gaming", "office"], tags_json=["mechanical", "rgb"], status="active",
    )
    mouse = Product(
        merchant_id=merchant.id, sku="CAT-MOUSE", name="Test Mouse", description="A wireless gaming mouse",
        price_amount=1500, currency="INR", category_id=category.id, stock_qty=0, stock_status="out_of_stock",
        use_cases_json=["gaming"], tags_json=["wireless"], status="active",
    )
    inactive_product = Product(
        merchant_id=merchant.id, sku="CAT-OLD", name="Discontinued Thing", price_amount=999, currency="INR",
        category_id=category.id, stock_qty=0, stock_status="in_stock", status="discontinued",
    )
    db.add_all([keyboard, mouse, inactive_product])
    db.flush()

    db.add(ProductRelation(product_id=keyboard.id, related_product_id=mouse.id, relation_type="FREQUENTLY_BOUGHT_WITH"))
    db.commit()

    yield db, merchant.id, keyboard.id, mouse.id, inactive_product.id
    reset_merchant(db, merchant.id)
    db.close()


def test_catalog_lists_only_active_products(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/catalog?merchant_id={merchant_id}")
    assert response.status_code == 200
    ids = {p["id"] for p in response.json()["items"]}
    assert str(keyboard_id) in ids
    assert str(mouse_id) in ids
    assert str(inactive_id) not in ids  # discontinued products never surface to an AI buyer


def test_out_of_stock_product_correctly_marked_unavailable(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/products/{mouse_id}?merchant_id={merchant_id}")
    body = response.json()
    assert body["availability"]["in_stock"] is False
    assert body["purchase"]["available"] is False


def test_in_stock_product_correctly_marked_available(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/products/{keyboard_id}?merchant_id={merchant_id}")
    body = response.json()
    assert body["availability"]["in_stock"] is True
    assert body["purchase"]["available"] is True
    assert body["price"]["amount"] == 3000.0  # exact real price, not rounded/estimated


def test_frequently_bought_with_reflects_real_product_relations_table(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/products/{keyboard_id}?merchant_id={merchant_id}")
    body = response.json()
    fbw_ids = {p["id"] for p in body["frequently_bought_with"]}
    assert str(mouse_id) in fbw_ids
    assert body["related_products"] == []  # no RELATED-type row was created - must not be fabricated


def test_nonexistent_product_returns_honest_404_not_fabricated_data(merchant_with_catalog):
    """The core anti-hallucination guarantee for the AI Buyer surface."""
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/products/{uuid.uuid4()}?merchant_id={merchant_id}")
    assert response.status_code == 404
    message = response.json()["error"]["message"].lower()
    assert "not found" in message or "no matching" in message


def test_search_by_price_range(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/catalog/search?merchant_id={merchant_id}&max_price=2000")
    ids = {p["id"] for p in response.json()["items"]}
    assert str(mouse_id) in ids  # 1500, under the cap
    assert str(keyboard_id) not in ids  # 3000, over the cap


def test_search_in_stock_only_excludes_out_of_stock(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/catalog/search?merchant_id={merchant_id}&in_stock_only=true")
    ids = {p["id"] for p in response.json()["items"]}
    assert str(mouse_id) not in ids  # out of stock
    assert str(keyboard_id) in ids


def test_search_by_text_query(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/catalog/search?merchant_id={merchant_id}&q=mechanical")
    ids = {p["id"] for p in response.json()["items"]}
    assert str(keyboard_id) in ids
    assert str(mouse_id) not in ids


def test_recommendations_match_real_use_cases_not_llm_generated(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/recommendations?merchant_id={merchant_id}&intent=gaming setup")
    body = response.json()
    assert body["found"] is True
    ids = {p["id"] for p in body["items"]}
    assert str(keyboard_id) in ids
    # mouse matches 'gaming' too but is out of stock - recommendations
    # must never suggest something that can't actually be purchased.
    assert str(mouse_id) not in ids


def test_recommendations_respect_max_price(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/recommendations?merchant_id={merchant_id}&intent=gaming&max_price=1000")
    body = response.json()
    assert body["found"] is False  # keyboard is 3000, over budget; mouse is out of stock anyway


def test_recommendations_with_no_match_returns_honest_empty_not_a_guess(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/recommendations?merchant_id={merchant_id}&intent=underwater basket weaving")
    body = response.json()
    assert body["found"] is False
    assert body["items"] == []


def test_categories_endpoint_returns_real_counts(merchant_with_catalog):
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    response = client.get(f"/api/v1/agent/categories?merchant_id={merchant_id}")
    body = response.json()
    category = next(c for c in body["items"] if c["name"] == "Test Gadgets")
    assert category["product_count"] == 2  # keyboard + mouse, NOT the discontinued item


def test_product_from_another_merchant_not_leaked(merchant_with_catalog):
    """Loophole check: listing merchant A's catalog must never include
    merchant B's products, and merchant A cannot fetch merchant B's
    product by ID even though the ID is technically valid in the DB."""
    db, merchant_id, keyboard_id, mouse_id, inactive_id = merchant_with_catalog
    other = Merchant(name=f"Other Catalog Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(other)
    db.flush()
    other_product = Product(merchant_id=other.id, sku="OTHER-1", name="Other Merchant Product", price_amount=100, stock_qty=5, stock_status="in_stock", status="active")
    db.add(other_product)
    db.commit()

    response = client.get(f"/api/v1/agent/catalog?merchant_id={merchant_id}")
    ids = {p["id"] for p in response.json()["items"]}
    assert str(other_product.id) not in ids

    cross_fetch = client.get(f"/api/v1/agent/products/{other_product.id}?merchant_id={merchant_id}")
    assert cross_fetch.status_code == 404

    reset_merchant(db, other.id)


def test_unknown_merchant_rejected():
    response = client.get(f"/api/v1/agent/catalog?merchant_id={uuid.uuid4()}")
    assert response.status_code == 404
