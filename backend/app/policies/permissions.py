"""Permission engine. This is the SOLE authority on whether an action
requires merchant approval, runs freely, or is denied outright — nothing
downstream (the agent's own reasoning, a prior turn's approval, an
optimistic assumption) can override what this returns.

Loophole deliberately closed: Emergency Stop is re-checked on every single
call, not cached at session start. If a merchant hits Emergency Stop mid-
session, the very next tool call is blocked — there's no window where a
session "grandfathers in" pre-stop permissions.
"""

import uuid
from enum import Enum

from sqlalchemy.orm import Session

from app.models.campaigns import AgentPermission
from app.models.identity import MerchantSettings

# Action codes that move or could move money, and are therefore always
# blocked outright under Emergency Stop regardless of their configured
# permission mode. Read/simulate/draft actions remain available so the
# merchant can still see analysis while financial actions are frozen.
FINANCIAL_ACTION_CODES = {
    "CREATE_DISCOUNT", "CREATE_PAYMENT_LINK", "CREATE_ORDER",
    "EXECUTE_FINANCIAL_ACTION", "CANCEL_PAYMENT_LINK", "REFUND_PAYMENT", "MODIFY_PRODUCT_PRICE",
}


class PermissionMode(str, Enum):
    ALLOW = "ALLOW"
    APPROVAL = "APPROVAL"
    DENY = "DENY"


def get_permission_mode(db: Session, merchant_id: uuid.UUID, action_code: str) -> PermissionMode:
    settings = db.query(MerchantSettings).filter(MerchantSettings.merchant_id == merchant_id).one_or_none()
    if settings and settings.emergency_stop_enabled and action_code in FINANCIAL_ACTION_CODES:
        return PermissionMode.DENY

    row = db.query(AgentPermission).filter(
        AgentPermission.merchant_id == merchant_id, AgentPermission.action_code == action_code
    ).one_or_none()
    if row is None:
        # Fail closed: an action code with no configured permission row is
        # treated as requiring approval, never as implicitly allowed.
        return PermissionMode.APPROVAL
    return PermissionMode(row.mode)
