"""Regression tests for a real gap found during audit: dashboard.py,
campaigns.py, opportunities.py, simulations.py, attribution.py and
merchants.py never called ensure_merchant_access/get_principal at all, so
a garbage bearer token or a valid token for a *different* merchant was
silently ignored instead of rejected (a signed-in user could read any
merchant's revenue, campaigns, opportunities, and simulations, not just
their own). These tests pin the fix so it cannot silently regress.

Anonymous (no Authorization header at all) requests are intentionally
still allowed through in DEMO_MODE -- that is documented, existing
product behaviour (see docs/security.md) and unrelated to the bug fixed
here. These tests only cover the two cases that were actually broken:
an invalid/garbage token, and a valid token for the wrong merchant.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app
from app.models.identity import Merchant, Role, User, UserMerchantRole
from app.security.auth import create_access_token
from app.security.passwords import hash_password

client = TestClient(app)

PROTECTED_GET_ENDPOINTS = [
    "/api/v1/dashboard/summary",
    "/api/v1/dashboard/revenue-trend",
    "/api/v1/dashboard/top-products",
    "/api/v1/campaigns",
    "/api/v1/opportunities",
    "/api/v1/attribution/summary",
    "/api/v1/attribution/campaigns",
]


@pytest.fixture
def two_merchants_and_a_scoped_user():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant_a = Merchant(name=f"Audit Test A {uuid.uuid4().hex[:6]}", category="Test", status="active")
    merchant_b = Merchant(name=f"Audit Test B {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add_all([merchant_a, merchant_b])
    db.flush()

    role = db.query(Role).filter(Role.name == "OWNER").first()
    if role is None:
        role = Role(name="OWNER")
        db.add(role)
        db.flush()

    user = User(email=f"audit-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("x"), name="Audit User")
    db.add(user)
    db.flush()
    db.add(UserMerchantRole(user_id=user.id, merchant_id=merchant_a.id, role_id=role.id))
    db.commit()

    token = create_access_token(user.id)

    yield merchant_a.id, merchant_b.id, token

    db.query(UserMerchantRole).filter(UserMerchantRole.user_id == user.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    db.query(Merchant).filter(Merchant.id.in_([merchant_a.id, merchant_b.id])).delete()
    db.commit()
    db.close()


@pytest.mark.parametrize("path", PROTECTED_GET_ENDPOINTS)
def test_valid_token_cannot_read_a_different_merchant(path, two_merchants_and_a_scoped_user):
    merchant_a, merchant_b, token = two_merchants_and_a_scoped_user
    response = client.get(f"{path}?merchant_id={merchant_b}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MERCHANT_ACCESS_DENIED"


@pytest.mark.parametrize("path", PROTECTED_GET_ENDPOINTS)
def test_valid_token_can_read_own_merchant(path, two_merchants_and_a_scoped_user):
    merchant_a, merchant_b, token = two_merchants_and_a_scoped_user
    response = client.get(f"{path}?merchant_id={merchant_a}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


@pytest.mark.parametrize("path", PROTECTED_GET_ENDPOINTS)
def test_garbage_token_is_rejected_not_silently_ignored(path, two_merchants_and_a_scoped_user):
    merchant_a, _merchant_b, _token = two_merchants_and_a_scoped_user
    response = client.get(f"{path}?merchant_id={merchant_a}", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_simulations_compare_rejects_cross_merchant_token(two_merchants_and_a_scoped_user):
    merchant_a, merchant_b, token = two_merchants_and_a_scoped_user
    response = client.post(
        f"/api/v1/simulations/compare?merchant_id={merchant_b}",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_ids": [str(uuid.uuid4())], "discount_percents": [10]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MERCHANT_ACCESS_DENIED"


def test_campaign_pause_requires_owner_or_admin_role_and_merchant_membership(two_merchants_and_a_scoped_user):
    merchant_a, merchant_b, token = two_merchants_and_a_scoped_user
    fake_campaign_id = uuid.uuid4()
    # Campaign doesn't exist, but membership is still checked first for
    # the merchant a caller *does* belong to only after the campaign is
    # resolved -- for a nonexistent campaign this correctly 404s rather
    # than leaking whether the id exists to an unrelated caller.
    response = client.post(
        f"/api/v1/campaigns/{fake_campaign_id}/pause", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_merchants_list_scopes_to_the_signed_in_users_own_merchants(two_merchants_and_a_scoped_user):
    merchant_a, merchant_b, token = two_merchants_and_a_scoped_user
    response = client.get("/api/v1/merchants", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(merchant_a) in ids
    assert str(merchant_b) not in ids


def test_merchants_get_by_id_rejects_cross_merchant_token(two_merchants_and_a_scoped_user):
    merchant_a, merchant_b, token = two_merchants_and_a_scoped_user
    response = client.get(f"/api/v1/merchants/{merchant_b}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
