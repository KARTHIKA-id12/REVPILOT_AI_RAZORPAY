import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.service import create_session, handle_message
from app.core.errors import AppError
from app.db.session import get_db
from app.models.agent import AgentAction, AgentMessage, AgentSession
from app.models.identity import Merchant
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class CreateSessionRequest(BaseModel):
    merchant_id: uuid.UUID
    channel: str = "merchant_console"


class SendMessageRequest(BaseModel):
    content: str


@router.post("/sessions")
def create_agent_session(
    body: CreateSessionRequest, principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    merchant = db.get(Merchant, body.merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)
    ensure_merchant_access(db, body.merchant_id, principal)
    session = create_session(db, body.merchant_id, user_id=None, channel=body.channel)
    return {"id": str(session.id), "status": session.status, "started_at": session.started_at.isoformat()}


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    merchant_id: uuid.UUID = Query(...),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    session = db.query(AgentSession).filter(
        AgentSession.id == session_id, AgentSession.merchant_id == merchant_id,
    ).one_or_none()
    if not session:
        raise AppError("SESSION_NOT_FOUND", "Agent session not found.", status_code=404)
    if not body.content or len(body.content.strip()) == 0:
        raise AppError("EMPTY_MESSAGE", "Message content cannot be empty.", status_code=422)

    result = handle_message(db, session, session.merchant_id, body.content)
    return result


@router.get("/sessions/{session_id}")
def get_session(
    session_id: uuid.UUID,
    merchant_id: uuid.UUID = Query(...),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    session = db.query(AgentSession).filter(
        AgentSession.id == session_id, AgentSession.merchant_id == merchant_id,
    ).one_or_none()
    if not session:
        raise AppError("SESSION_NOT_FOUND", "Agent session not found.", status_code=404)
    messages = db.query(AgentMessage).filter(AgentMessage.session_id == session_id).order_by(AgentMessage.created_at).all()
    return {
        "id": str(session.id), "status": session.status, "channel": session.channel,
        "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in messages],
    }


@router.get("/actions")
def list_agent_actions(
    merchant_id: uuid.UUID, status: str | None = None, page: int = 1, page_size: int = 20,
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    query = (
        db.query(AgentAction)
        .join(AgentSession, AgentSession.id == AgentAction.session_id)
        .filter(AgentSession.merchant_id == merchant_id)
    )
    if status:
        query = query.filter(AgentAction.status == status)
    total = query.count()
    rows = query.order_by(AgentAction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": str(a.id), "action_code": a.action_code, "status": a.status, "risk_level": a.risk_level,
                "permission_result": a.permission_result, "approval_id": str(a.approval_id) if a.approval_id else None,
                "error": a.error, "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ],
        "page": page, "page_size": page_size, "total": total,
    }
