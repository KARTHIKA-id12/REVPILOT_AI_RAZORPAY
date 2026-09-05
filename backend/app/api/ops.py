import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant
from app.models.ops import Notification
from app.ops.service import action_center, get_trace, list_audit, list_notifications, list_traces
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/ops", tags=["operations"])


def _require_merchant(db: Session, merchant_id: uuid.UUID) -> None:
    if not db.get(Merchant, merchant_id):
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)


@router.get("/audit")
def audit_ledger(
    merchant_id: uuid.UUID,
    result: str | None = Query(default=None),
    action: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    items, total = list_audit(
        db, merchant_id, result=result, action=action, search=search, since=since, until=until,
        offset=offset, limit=limit,
    )
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/traces")
def agent_traces(
    merchant_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    items, total = list_traces(db, merchant_id, offset=offset, limit=limit)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/traces/{session_id}")
def agent_trace(
    session_id: uuid.UUID, merchant_id: uuid.UUID, principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    trace = get_trace(db, merchant_id, session_id)
    if not trace:
        raise AppError("TRACE_NOT_FOUND", "Agent session not found.", status_code=404)
    return trace


@router.get("/action-center")
def get_action_center(
    merchant_id: uuid.UUID, principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    return action_center(db, merchant_id)


@router.get("/notifications")
def notifications(
    merchant_id: uuid.UUID,
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    items, total = list_notifications(db, merchant_id, unread_only=unread_only, limit=limit)
    return {"items": items, "total": total}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: uuid.UUID, merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    notification = db.query(Notification).filter(
        Notification.id == notification_id, Notification.merchant_id == merchant_id,
    ).one_or_none()
    if not notification:
        raise AppError("NOTIFICATION_NOT_FOUND", "Notification not found.", status_code=404)
    notification.read_at = datetime.now(datetime.UTC)
    db.commit()
    return {"id": str(notification.id), "read_at": notification.read_at.isoformat()}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    merchant_id: uuid.UUID, principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    ensure_merchant_access(db, merchant_id, principal)
    count = db.query(Notification).filter(
        Notification.merchant_id == merchant_id, Notification.read_at.is_(None),
    ).update({"read_at": datetime.now(datetime.UTC)}, synchronize_session=False)
    db.commit()
    return {"marked_read": count}