import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant, UserMerchantRole
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/merchants", tags=["merchants"])


def _serialize(m: Merchant) -> dict:
    return {"id": str(m.id), "name": m.name, "category": m.category, "description": m.description, "status": m.status}


@router.get("")
def list_merchants(
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """In DEMO_MODE with no bearer token, this lists every active
    merchant so the seeded demo frontend can discover TechNest without a
    login flow. Once a real principal is present (demo or not), the list
    always narrows to merchants that principal actually belongs to —
    this was a real gap found during audit: a valid signed-in user could
    previously see every merchant on the platform, not just their own."""
    from app.core.config import get_settings

    query = db.query(Merchant).filter(Merchant.status == "active")
    if principal is not None:
        query = query.join(UserMerchantRole, UserMerchantRole.merchant_id == Merchant.id).filter(
            UserMerchantRole.user_id == principal.user_id,
        )
    elif not get_settings().DEMO_MODE:
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in is required.", status_code=401)
    merchants = query.all()
    return {"items": [_serialize(m) for m in merchants]}


@router.get("/{merchant_id}")
def get_merchant(
    merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)
    return _serialize(merchant)
