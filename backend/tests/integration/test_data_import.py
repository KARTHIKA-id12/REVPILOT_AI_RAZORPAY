"""End-to-end tests for the CSV data-import feature -- lets a merchant
bring their own customer/order history for real analysis instead of only
ever seeing the seeded demo data. Exercises the real HTTP API, not just
the service function, so auth/role enforcement is covered too.
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app
from app.models.catalog import Product
from app.models.commerce import Order
from app.models.customers import Customer
from app.models.identity import Merchant, MerchantSettings, Role, User, UserMerchantRole
from app.security.auth import create_access_token
from app.security.passwords import hash_password
from app.services.merchant_cleanup import reset_merchant

client = TestClient(app)


@pytest.fixture
def upload_merchant():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Upload Test {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))
    db.add(Product(merchant_id=merchant.id, sku="UP-SKU-1", name="Uploaded Product", price_amount=999, stock_qty=10, stock_status="in_stock"))

    role = db.query(Role).filter(Role.name == "OWNER").first() or Role(name="OWNER")
    db.add(role)
    db.flush()
    owner = User(email=f"owner-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("x"), name="Owner")
    db.add(owner)
    db.flush()
    db.add(UserMerchantRole(user_id=owner.id, merchant_id=merchant.id, role_id=role.id))

    viewer_role = db.query(Role).filter(Role.name == "VIEWER").first() or Role(name="VIEWER")
    db.add(viewer_role)
    db.flush()
    viewer = User(email=f"viewer-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("x"), name="Viewer")
    db.add(viewer)
    db.flush()
    db.add(UserMerchantRole(user_id=viewer.id, merchant_id=merchant.id, role_id=viewer_role.id))
    db.commit()

    owner_token = create_access_token(owner.id)
    viewer_token = create_access_token(viewer.id)

    yield db, merchant.id, owner_token, viewer_token

    db.query(UserMerchantRole).filter(UserMerchantRole.user_id.in_([owner.id, viewer.id])).delete()
    db.query(User).filter(User.id.in_([owner.id, viewer.id])).delete()
    reset_merchant(db, merchant.id)
    db.commit()
    db.close()


def _csv_file(text: str, name: str = "data.csv"):
    return {"file": (name, io.BytesIO(text.encode("utf-8")), "text/csv")}


def test_upload_schema_is_discoverable_without_auth():
    response = client.get("/api/v1/data/schema")
    assert response.status_code == 200
    assert "customers_csv" in response.json()
    assert "orders_csv" in response.json()


def test_customers_csv_import_creates_and_dedupes(upload_merchant):
    db, merchant_id, owner_token, _viewer_token = upload_merchant
    csv_text = "name,email,phone\nAda Lovelace,ada@example.com,\nGrace Hopper,grace@example.com,\n"

    response = client.post(
        f"/api/v1/data/upload/customers?merchant_id={merchant_id}",
        files=_csv_file(csv_text), headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["customers_created"] == 2
    assert body["customers_matched_existing"] == 0

    # Re-uploading the same file should match existing customers by email, not duplicate them.
    response2 = client.post(
        f"/api/v1/data/upload/customers?merchant_id={merchant_id}",
        files=_csv_file(csv_text), headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response2.status_code == 200
    assert response2.json()["customers_created"] == 0
    assert response2.json()["customers_matched_existing"] == 2


def test_orders_csv_import_creates_orders_and_refreshes_analytics(upload_merchant):
    db, merchant_id, owner_token, _viewer_token = upload_merchant
    csv_text = (
        "customer_email,total_amount,status,created_at,product_skus\n"
        "buyer1@example.com,999,paid,2026-01-10,UP-SKU-1\n"
        "buyer2@example.com,1998,paid,2026-02-15,UP-SKU-1\n"
        "buyer1@example.com,999,paid,2026-03-01,UP-SKU-1\n"
    )
    response = client.post(
        f"/api/v1/data/upload/orders?merchant_id={merchant_id}",
        files=_csv_file(csv_text), headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["orders_created"] == 3
    assert body["rows_skipped"] == []
    assert "analytics_refreshed" in body
    assert "opportunities_detected" in body["analytics_refreshed"]

    orders = db.query(Order).filter(Order.merchant_id == merchant_id).all()
    assert len(orders) == 3
    assert all(o.source == "imported" for o in orders)

    buyer1 = db.query(Customer).filter(Customer.merchant_id == merchant_id, Customer.email == "buyer1@example.com").first()
    assert buyer1 is not None
    assert buyer1.order_count == 2
    assert float(buyer1.total_spend) == pytest.approx(1998.0)


def test_orders_csv_reports_bad_rows_without_failing_the_whole_import(upload_merchant):
    db, merchant_id, owner_token, _viewer_token = upload_merchant
    csv_text = (
        "customer_email,total_amount,status,created_at,product_skus\n"
        "good@example.com,500,paid,2026-01-10,\n"
        ",500,paid,2026-01-10,\n"                       # missing email
        "bad-status@example.com,500,shipped,2026-01-10,\n"  # invalid status
        "bad-amount@example.com,not-a-number,paid,2026-01-10,\n"
        "bad-date@example.com,500,paid,not-a-date,\n"
    )
    response = client.post(
        f"/api/v1/data/upload/orders?merchant_id={merchant_id}",
        files=_csv_file(csv_text), headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["orders_created"] == 1
    assert len(body["rows_skipped"]) == 4


def test_missing_required_column_is_rejected(upload_merchant):
    _db, merchant_id, owner_token, _viewer_token = upload_merchant
    csv_text = "email\nada@example.com\n"  # missing required 'name' column for customers
    response = client.post(
        f"/api/v1/data/upload/customers?merchant_id={merchant_id}",
        files=_csv_file(csv_text), headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CSV"


def test_viewer_role_cannot_upload_data(upload_merchant):
    """Matches the restriction already used for settings/approvals: a
    VIEWER can look at analytics but must not be able to mutate the
    merchant's core dataset."""
    _db, merchant_id, _owner_token, viewer_token = upload_merchant
    csv_text = "name,email\nSomeone,someone@example.com\n"
    response = client.post(
        f"/api/v1/data/upload/customers?merchant_id={merchant_id}",
        files=_csv_file(csv_text), headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == 403


def test_upload_requires_merchant_membership(upload_merchant):
    _db, _merchant_id, owner_token, _viewer_token = upload_merchant
    other_merchant_id = uuid.uuid4()
    csv_text = "name,email\nSomeone,someone@example.com\n"
    response = client.post(
        f"/api/v1/data/upload/customers?merchant_id={other_merchant_id}",
        files=_csv_file(csv_text), headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code in (403, 404)
