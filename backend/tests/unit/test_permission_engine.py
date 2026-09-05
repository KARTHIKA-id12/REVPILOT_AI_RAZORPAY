import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.campaigns import AgentPermission
from app.models.identity import Merchant, MerchantSettings
from app.policies.permissions import PermissionMode, get_permission_mode


@pytest.fixture
def db_with_merchant():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Perm Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()
    db.add(MerchantSettings(merchant_id=merchant.id))
    db.add(AgentPermission(merchant_id=merchant.id, action_code="CREATE_PAYMENT_LINK", mode="APPROVAL"))
    db.add(AgentPermission(merchant_id=merchant.id, action_code="VIEW_ANALYTICS", mode="ALLOW"))
    db.add(AgentPermission(merchant_id=merchant.id, action_code="REFUND_PAYMENT", mode="DENY"))
    db.flush()
    yield db, merchant.id
    db.rollback()
    db.close()


def test_configured_permission_is_honored(db_with_merchant):
    db, merchant_id = db_with_merchant
    assert get_permission_mode(db, merchant_id, "VIEW_ANALYTICS") == PermissionMode.ALLOW
    assert get_permission_mode(db, merchant_id, "CREATE_PAYMENT_LINK") == PermissionMode.APPROVAL
    assert get_permission_mode(db, merchant_id, "REFUND_PAYMENT") == PermissionMode.DENY


def test_unconfigured_action_fails_closed_to_approval(db_with_merchant):
    """No permission row exists for this action code — the engine must
    NOT interpret that as implicit ALLOW."""
    db, merchant_id = db_with_merchant
    assert get_permission_mode(db, merchant_id, "SOME_NEW_ACTION_CODE") == PermissionMode.APPROVAL


def test_emergency_stop_overrides_allow_for_financial_actions(db_with_merchant):
    db, merchant_id = db_with_merchant
    db.add(AgentPermission(merchant_id=merchant_id, action_code="CREATE_ORDER", mode="ALLOW"))
    db.flush()
    assert get_permission_mode(db, merchant_id, "CREATE_ORDER") == PermissionMode.ALLOW

    settings = db.query(MerchantSettings).filter(MerchantSettings.merchant_id == merchant_id).one()
    settings.emergency_stop_enabled = True
    db.flush()

    assert get_permission_mode(db, merchant_id, "CREATE_ORDER") == PermissionMode.DENY


def test_emergency_stop_does_not_block_read_actions(db_with_merchant):
    """The merchant should still be able to see analytics/simulation while
    financial actions are frozen — Emergency Stop is not a full outage."""
    db, merchant_id = db_with_merchant
    settings = db.query(MerchantSettings).filter(MerchantSettings.merchant_id == merchant_id).one()
    settings.emergency_stop_enabled = True
    db.flush()

    assert get_permission_mode(db, merchant_id, "VIEW_ANALYTICS") == PermissionMode.ALLOW


def test_emergency_stop_is_re_evaluated_every_call_not_cached(db_with_merchant):
    db, merchant_id = db_with_merchant
    db.add(AgentPermission(merchant_id=merchant_id, action_code="CREATE_ORDER", mode="ALLOW"))
    settings = db.query(MerchantSettings).filter(MerchantSettings.merchant_id == merchant_id).one()
    db.flush()

    assert get_permission_mode(db, merchant_id, "CREATE_ORDER") == PermissionMode.ALLOW
    settings.emergency_stop_enabled = True
    db.flush()
    assert get_permission_mode(db, merchant_id, "CREATE_ORDER") == PermissionMode.DENY
    settings.emergency_stop_enabled = False
    db.flush()
    assert get_permission_mode(db, merchant_id, "CREATE_ORDER") == PermissionMode.ALLOW
