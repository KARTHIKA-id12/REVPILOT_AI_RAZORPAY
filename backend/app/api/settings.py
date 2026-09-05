import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.campaigns import AgentPermission, PolicyRule
from app.models.identity import Merchant, MerchantSettings
from app.policies.constants import PERMISSION_ACTION_CODES, PERMISSION_MODES, POLICY_DEFINITIONS
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _require_merchant(db: Session, merchant_id: uuid.UUID) -> Merchant:
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)
    return merchant


# --- Permissions -------------------------------------------------------

class PermissionUpdate(BaseModel):
    action_code: str
    mode: str

    @field_validator("action_code")
    @classmethod
    def known_action_code(cls, v: str) -> str:
        if v not in PERMISSION_ACTION_CODES:
            raise ValueError(f"Unknown action_code '{v}'. Must be one of: {sorted(PERMISSION_ACTION_CODES)}")
        return v

    @field_validator("mode")
    @classmethod
    def known_mode(cls, v: str) -> str:
        if v not in PERMISSION_MODES:
            raise ValueError(f"Unknown mode '{v}'. Must be one of: {sorted(PERMISSION_MODES)}")
        return v


class UpdatePermissionsRequest(BaseModel):
    permissions: list[PermissionUpdate]


@router.get("/permissions")
def get_permissions(
    merchant_id: uuid.UUID, principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    existing = {p.action_code: p.mode for p in db.query(AgentPermission).filter(AgentPermission.merchant_id == merchant_id)}
    return {
        "items": [
            {
                "action_code": code, "description": description,
                "mode": existing.get(code, "APPROVAL"),  # matches the permission engine's fail-closed default
            }
            for code, description in PERMISSION_ACTION_CODES.items()
        ]
    }


@router.put("/permissions")
def update_permissions(
    merchant_id: uuid.UUID, body: UpdatePermissionsRequest,
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    """Every update is an UPSERT on (merchant_id, action_code) — the DB's
    unique constraint on that pair (added after a real bug in Phase 7)
    guarantees there is never more than one row per action, so this can
    never create the duplicate-row situation that used to crash the
    permission engine."""
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    existing = {p.action_code: p for p in db.query(AgentPermission).filter(AgentPermission.merchant_id == merchant_id)}

    for update in body.permissions:
        if update.action_code in existing:
            existing[update.action_code].mode = update.mode
        else:
            db.add(AgentPermission(merchant_id=merchant_id, action_code=update.action_code, mode=update.mode))
    db.commit()
    return get_permissions(merchant_id, principal, db)


# --- Policies ------------------------------------------------------------

class PolicyUpdate(BaseModel):
    code: str
    value: bool | float | int

    @field_validator("code")
    @classmethod
    def known_code(cls, v: str) -> str:
        if v not in POLICY_DEFINITIONS:
            raise ValueError(f"Unknown policy code '{v}'. Must be one of: {sorted(POLICY_DEFINITIONS)}")
        return v


class UpdatePoliciesRequest(BaseModel):
    policies: list[PolicyUpdate]


def _default_for(code: str):
    defaults = {
        "MAX_DISCOUNT_PERCENT": 15, "MAX_CAMPAIGN_BUDGET": 5000, "MAX_DAILY_CAMPAIGNS": 10,
        "MAX_SINGLE_TRANSACTION": 10000, "REQUIRE_APPROVAL_FOR_FINANCIAL_ACTIONS": True,
        "NO_OUT_OF_STOCK_PRODUCTS": True, "NO_NEGATIVE_MARGIN_ACTIONS": True,
    }
    return defaults[code]


@router.get("/policies")
def get_policies(
    merchant_id: uuid.UUID, principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    existing = {p.code: p.value_json.get("value") for p in db.query(PolicyRule).filter(PolicyRule.merchant_id == merchant_id)}
    return {
        "items": [
            {**definition, "code": code, "value": existing.get(code, _default_for(code))}
            for code, definition in POLICY_DEFINITIONS.items()
        ]
    }


@router.put("/policies")
def update_policies(
    merchant_id: uuid.UUID, body: UpdatePoliciesRequest,
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})

    for update in body.policies:
        definition = POLICY_DEFINITIONS[update.code]
        if definition["type"] in {"percent", "amount", "count"}:
            numeric_value = float(update.value)
            min_val, max_val = definition.get("min"), definition.get("max")
            if min_val is not None and numeric_value < min_val:
                raise AppError("INVALID_POLICY_VALUE", f"{update.code} cannot be below {min_val}.", status_code=422)
            if max_val is not None and numeric_value > max_val:
                raise AppError("INVALID_POLICY_VALUE", f"{update.code} cannot exceed {max_val}.", status_code=422)

    existing = {p.code: p for p in db.query(PolicyRule).filter(PolicyRule.merchant_id == merchant_id)}
    for update in body.policies:
        if update.code in existing:
            existing[update.code].value_json = {"value": update.value}
        else:
            db.add(PolicyRule(merchant_id=merchant_id, code=update.code, value_json={"value": update.value}))
    db.commit()
    return get_policies(merchant_id, principal, db)


# --- Emergency Stop --------------------------------------------------------

class EmergencyStopRequest(BaseModel):
    enabled: bool


@router.get("/emergency-stop")
def get_emergency_stop(
    merchant_id: uuid.UUID, principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    settings = db.query(MerchantSettings).filter(MerchantSettings.merchant_id == merchant_id).one_or_none()
    return {"enabled": bool(settings.emergency_stop_enabled) if settings else False}


@router.post("/emergency-stop")
def set_emergency_stop(
    merchant_id: uuid.UUID, body: EmergencyStopRequest,
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    settings = db.query(MerchantSettings).filter(MerchantSettings.merchant_id == merchant_id).one_or_none()
    if not settings:
        settings = MerchantSettings(merchant_id=merchant_id)
        db.add(settings)
    settings.emergency_stop_enabled = body.enabled
    db.commit()
    return {"enabled": settings.emergency_stop_enabled}
