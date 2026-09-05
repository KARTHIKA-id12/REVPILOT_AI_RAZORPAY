import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.campaigns import ApprovalRequest, Campaign
from app.models.catalog import Product
from app.models.commerce import Payment
from app.models.ops import AuditLog
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])

# Statuses from which a pause/cancel is a meaningful, well-defined
# transition. Anything else is rejected rather than silently accepted —
# e.g. cancelling an already-cancelled campaign, or pausing a draft that
# was never running, would otherwise corrupt the status history.
PAUSABLE_STATUSES = {"running"}
CANCELLABLE_STATUSES = {"draft", "pending_approval", "approved", "running", "paused"}


def _serialize_summary(c: Campaign) -> dict:
    return {
        "id": str(c.id), "name": c.name, "objective": c.objective, "status": c.status,
        "discount_percent": float(c.discount_percent), "budget_amount": float(c.budget_amount),
        "expected_revenue_amount": float(c.expected_revenue_amount), "actual_revenue_amount": float(c.actual_revenue_amount),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "starts_at": c.starts_at.isoformat() if c.starts_at else None,
    }


@router.get("")
def list_campaigns(
    merchant_id: uuid.UUID, status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    query = db.query(Campaign).filter(Campaign.merchant_id == merchant_id)
    if status:
        query = query.filter(Campaign.status == status)
    total = query.count()
    rows = query.order_by(Campaign.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_serialize_summary(c) for c in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign not found.", status_code=404)
    ensure_merchant_access(db, campaign.merchant_id, principal)

    product_ids = [uuid.UUID(p) for p in (campaign.product_ids_json or [])]
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids))} if product_ids else {}

    approvals = db.query(ApprovalRequest).filter(ApprovalRequest.campaign_id == campaign_id).order_by(ApprovalRequest.created_at).all()
    payments = db.query(Payment).filter(Payment.campaign_id == campaign_id).order_by(Payment.created_at).all()

    approval_ids = [a.id for a in approvals]
    payment_ids = [p.id for p in payments]
    audit_filters = [AuditLog.external_id == str(campaign_id)]
    if approval_ids:
        audit_filters.append(AuditLog.approval_id.in_(approval_ids))
    if payment_ids:
        audit_filters.append(AuditLog.external_id.in_([str(p) for p in payment_ids]))

    audit_trail = (
        db.query(AuditLog)
        .filter(AuditLog.merchant_id == campaign.merchant_id, or_(*audit_filters))
        .order_by(AuditLog.created_at)
        .all()
    )

    return {
        **_serialize_summary(campaign),
        "opportunity_id": str(campaign.opportunity_id) if campaign.opportunity_id else None,
        "products": [{"id": str(pid), "name": p.name} for pid, p in products.items()],
        "approval_history": [
            {
                "id": str(a.id), "status": a.status, "risk_level": a.risk_level,
                "policy_result": a.policy_result_json, "created_at": a.created_at.isoformat() if a.created_at else None,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            }
            for a in approvals
        ],
        "payments": [
            {
                "id": str(p.id), "provider": p.provider, "status": p.status, "amount": float(p.amount),
                "provider_payment_link_id": p.provider_payment_link_id, "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ],
        "audit_trail": [
            {
                "action": e.action, "tool": e.tool, "reason": e.reason, "result": e.result,
                "error": e.error, "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in audit_trail
        ],
    }


@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign not found.", status_code=404)
    ensure_merchant_access(db, campaign.merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    if campaign.status not in PAUSABLE_STATUSES:
        raise AppError(
            "INVALID_STATUS_TRANSITION", f"Cannot pause a campaign in '{campaign.status}' status (must be running).",
            status_code=409,
        )
    campaign.status = "paused"
    db.add(AuditLog(
        merchant_id=campaign.merchant_id, action="PAUSE_CAMPAIGN", tool="pause_campaign",
        input_summary=f"campaign={campaign_id}", reason="merchant requested pause", result="success",
        external_id=str(campaign_id), created_at=datetime.now(UTC),
    ))
    db.commit()
    return {"status": campaign.status}


@router.post("/{campaign_id}/cancel")
def cancel_campaign(
    campaign_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign not found.", status_code=404)
    ensure_merchant_access(db, campaign.merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    if campaign.status not in CANCELLABLE_STATUSES:
        raise AppError(
            "INVALID_STATUS_TRANSITION", f"Cannot cancel a campaign in '{campaign.status}' status.", status_code=409,
        )
    campaign.status = "cancelled"
    db.add(AuditLog(
        merchant_id=campaign.merchant_id, action="CANCEL_CAMPAIGN", tool="cancel_campaign",
        input_summary=f"campaign={campaign_id}", reason="merchant requested cancellation", result="success",
        external_id=str(campaign_id), created_at=datetime.now(UTC),
    ))
    db.commit()
    return {"status": campaign.status}
