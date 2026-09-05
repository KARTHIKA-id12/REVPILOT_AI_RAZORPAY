import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.pipeline import decide_approval
from app.core.errors import AppError
from app.db.session import get_db
from app.models.campaigns import ApprovalRequest
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


def _serialize(approval: ApprovalRequest) -> dict:
    return {
        "id": str(approval.id),
        "campaign_id": str(approval.campaign_id) if approval.campaign_id else None,
        "action_code": approval.action_code,
        "payload": approval.payload_json,
        "risk_level": approval.risk_level,
        "policy_result": approval.policy_result_json,
        "status": approval.status,
        "created_at": approval.created_at.isoformat() if approval.created_at else None,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
    }


@router.get("")
def list_approvals(
    merchant_id: uuid.UUID, status: str = "pending",
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    query = db.query(ApprovalRequest).filter(ApprovalRequest.merchant_id == merchant_id)
    if status != "all":
        query = query.filter(ApprovalRequest.status == status)
    rows = query.order_by(ApprovalRequest.created_at.desc()).all()
    return {"items": [_serialize(a) for a in rows]}


@router.post("/{approval_id}/approve")
def approve(
    approval_id: uuid.UUID, merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    result = decide_approval(db, merchant_id, approval_id, "approve", decided_by_user_id=None)
    if "error" in result:
        raise AppError("APPROVAL_ERROR", result["error"], status_code=400)
    return result


@router.post("/{approval_id}/reject")
def reject(
    approval_id: uuid.UUID, merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    result = decide_approval(db, merchant_id, approval_id, "reject", decided_by_user_id=None)
    if "error" in result:
        raise AppError("APPROVAL_ERROR", result["error"], status_code=400)
    return result
