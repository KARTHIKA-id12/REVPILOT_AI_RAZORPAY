import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app
from app.models.campaigns import AgentPermission, PolicyRule
from app.models.identity import Merchant, MerchantSettings

client = TestClient(app)


@pytest.fixture
def merchant():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    m = Merchant(name=f"Settings Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(m)
    db.flush()
    db.add(MerchantSettings(merchant_id=m.id))
    db.commit()
    yield m.id
    db.query(AgentPermission).filter(AgentPermission.merchant_id == m.id).delete()
    db.query(PolicyRule).filter(PolicyRule.merchant_id == m.id).delete()
    db.query(MerchantSettings).filter(MerchantSettings.merchant_id == m.id).delete()
    db.query(Merchant).filter(Merchant.id == m.id).delete()
    db.commit()
    db.close()


def test_get_permissions_returns_fail_closed_default_for_unconfigured_action(merchant):
    response = client.get(f"/api/v1/settings/permissions?merchant_id={merchant}")
    assert response.status_code == 200
    items = {i["action_code"]: i["mode"] for i in response.json()["items"]}
    assert items["REFUND_PAYMENT"] == "APPROVAL"  # no row configured yet -> fail-closed default, not ALLOW


def test_update_permission_upserts_and_is_reflected_immediately(merchant):
    response = client.put(
        f"/api/v1/settings/permissions?merchant_id={merchant}",
        json={"permissions": [{"action_code": "CREATE_PAYMENT_LINK", "mode": "ALLOW"}]},
    )
    assert response.status_code == 200
    items = {i["action_code"]: i["mode"] for i in response.json()["items"]}
    assert items["CREATE_PAYMENT_LINK"] == "ALLOW"

    # updating again must UPDATE the existing row, not insert a duplicate
    response2 = client.put(
        f"/api/v1/settings/permissions?merchant_id={merchant}",
        json={"permissions": [{"action_code": "CREATE_PAYMENT_LINK", "mode": "DENY"}]},
    )
    items2 = {i["action_code"]: i["mode"] for i in response2.json()["items"]}
    assert items2["CREATE_PAYMENT_LINK"] == "DENY"


def test_unknown_action_code_rejected_not_silently_stored(merchant):
    """Loophole check: a made-up action_code must never be accepted —
    storing it would give false confidence that a control exists when
    the Action Pipeline never checks that code at all."""
    response = client.put(
        f"/api/v1/settings/permissions?merchant_id={merchant}",
        json={"permissions": [{"action_code": "DEFINITELY_NOT_A_REAL_ACTION", "mode": "ALLOW"}]},
    )
    assert response.status_code == 422


def test_unknown_permission_mode_rejected(merchant):
    response = client.put(
        f"/api/v1/settings/permissions?merchant_id={merchant}",
        json={"permissions": [{"action_code": "CREATE_ORDER", "mode": "MAYBE"}]},
    )
    assert response.status_code == 422


def test_get_policies_returns_spec_defaults(merchant):
    response = client.get(f"/api/v1/settings/policies?merchant_id={merchant}")
    items = {i["code"]: i["value"] for i in response.json()["items"]}
    assert items["MAX_DISCOUNT_PERCENT"] == 15
    assert items["MAX_CAMPAIGN_BUDGET"] == 5000


def test_update_policy_within_bounds_succeeds(merchant):
    response = client.put(
        f"/api/v1/settings/policies?merchant_id={merchant}",
        json={"policies": [{"code": "MAX_DISCOUNT_PERCENT", "value": 20}]},
    )
    assert response.status_code == 200
    items = {i["code"]: i["value"] for i in response.json()["items"]}
    assert items["MAX_DISCOUNT_PERCENT"] == 20


def test_update_policy_out_of_bounds_rejected(merchant):
    """A discount cap over 100% is nonsensical and must be rejected at
    the settings layer — not silently accepted and then relied upon by
    the policy engine to produce confusing downstream behavior."""
    response = client.put(
        f"/api/v1/settings/policies?merchant_id={merchant}",
        json={"policies": [{"code": "MAX_DISCOUNT_PERCENT", "value": 150}]},
    )
    assert response.status_code == 422


def test_negative_budget_rejected(merchant):
    response = client.put(
        f"/api/v1/settings/policies?merchant_id={merchant}",
        json={"policies": [{"code": "MAX_CAMPAIGN_BUDGET", "value": -500}]},
    )
    assert response.status_code == 422


def test_unknown_policy_code_rejected(merchant):
    response = client.put(
        f"/api/v1/settings/policies?merchant_id={merchant}",
        json={"policies": [{"code": "NOT_A_REAL_POLICY", "value": 5}]},
    )
    assert response.status_code == 422


def test_emergency_stop_toggle_round_trips(merchant):
    initial = client.get(f"/api/v1/settings/emergency-stop?merchant_id={merchant}")
    assert initial.json()["enabled"] is False

    enable = client.post(f"/api/v1/settings/emergency-stop?merchant_id={merchant}", json={"enabled": True})
    assert enable.json()["enabled"] is True

    check = client.get(f"/api/v1/settings/emergency-stop?merchant_id={merchant}")
    assert check.json()["enabled"] is True

    disable = client.post(f"/api/v1/settings/emergency-stop?merchant_id={merchant}", json={"enabled": False})
    assert disable.json()["enabled"] is False


def test_emergency_stop_via_settings_actually_blocks_the_permission_engine(merchant):
    """End-to-end: flipping the toggle through the real settings endpoint
    must be observed by the real permission engine — not just stored."""
    from app.policies.permissions import PermissionMode, get_permission_mode

    db = SessionLocal()
    try:
        db.add(AgentPermission(merchant_id=merchant, action_code="CREATE_ORDER", mode="ALLOW"))
        db.commit()
        assert get_permission_mode(db, merchant, "CREATE_ORDER") == PermissionMode.ALLOW

        client.post(f"/api/v1/settings/emergency-stop?merchant_id={merchant}", json={"enabled": True})
        db.expire_all()
        assert get_permission_mode(db, merchant, "CREATE_ORDER") == PermissionMode.DENY
    finally:
        db.close()


def test_settings_endpoints_reject_unknown_merchant():
    fake_id = uuid.uuid4()
    response = client.get(f"/api/v1/settings/permissions?merchant_id={fake_id}")
    assert response.status_code == 404
