"""Read models and notification helpers for Phase 19 operational visibility.

The operational surfaces deliberately expose the persisted records produced by
the action pipeline. They do not reconstruct a second, UI-only history.
"""

import uuid
from datetime import timezone,  datetime, timedelta
UTC = timezone.utc

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.agent import AgentAction, AgentMessage, AgentSession, AgentToolCall
from app.models.campaigns import ApprovalRequest
from app.models.ops import AuditLog, Notification


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_audit(row: AuditLog) -> dict:
    return {
        "id": str(row.id),
        "merchant_id": str(row.merchant_id),
        "agent_session_id": str(row.agent_session_id) if row.agent_session_id else None,
        "action": row.action,
        "tool": row.tool,
        "input_summary": row.input_summary,
        "reason": row.reason,
        "policy_result": row.policy_result,
        "permission_result": row.permission_result,
        "approval_id": str(row.approval_id) if row.approval_id else None,
        "external_id": row.external_id,
        "result": row.result,
        "error": row.error,
        "recovery_action": row.recovery_action,
        "request_id": row.request_id,
        "created_at": _iso(row.created_at),
    }


def list_audit(
    db: Session,
    merchant_id: uuid.UUID,
    *,
    result: str | None = None,
    action: str | None = None,
    search: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    query = db.query(AuditLog).filter(AuditLog.merchant_id == merchant_id)
    if result:
        query = query.filter(AuditLog.result == result)
    if action:
        query = query.filter(AuditLog.action == action)
    if since:
        query = query.filter(AuditLog.created_at >= since)
    if until:
        query = query.filter(AuditLog.created_at <= until)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            AuditLog.action.ilike(term),
            AuditLog.tool.ilike(term),
            AuditLog.input_summary.ilike(term),
            AuditLog.reason.ilike(term),
            AuditLog.error.ilike(term),
            AuditLog.external_id.ilike(term),
        ))
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return [serialize_audit(row) for row in rows], total


def _serialize_session(session: AgentSession, *, include_trace: bool = False, db: Session | None = None) -> dict:
    result = {
        "id": str(session.id),
        "channel": session.channel,
        "status": session.status,
        "started_at": _iso(session.started_at),
        "ended_at": _iso(session.ended_at),
        "message_count": 0,
        "tool_call_count": 0,
        "action_count": 0,
        "last_activity_at": _iso(session.started_at),
    }
    if db is None:
        return result

    messages = db.query(AgentMessage).filter(AgentMessage.session_id == session.id).order_by(AgentMessage.created_at).all()
    tool_calls = db.query(AgentToolCall).filter(AgentToolCall.session_id == session.id).order_by(AgentToolCall.created_at).all()
    actions = db.query(AgentAction).filter(AgentAction.session_id == session.id).order_by(AgentAction.created_at).all()
    activities = [item.created_at for item in [*messages, *tool_calls, *actions] if item.created_at]
    result.update({
        "message_count": len(messages),
        "tool_call_count": len(tool_calls),
        "action_count": len(actions),
        "last_activity_at": _iso(max(activities, default=session.started_at)),
    })
    if include_trace:
        result["messages"] = [{
            "id": str(item.id), "role": item.role, "content": item.content, "created_at": _iso(item.created_at),
        } for item in messages]
        result["tool_calls"] = [{
            "id": str(item.id), "tool_name": item.tool_name, "input": item.input_json,
            "output": item.output_json, "latency_ms": item.latency_ms, "status": item.status,
            "created_at": _iso(item.created_at),
        } for item in tool_calls]
        result["actions"] = [{
            "id": str(item.id), "action_code": item.action_code, "input": item.input_json,
            "policy_result": item.policy_result, "permission_result": item.permission_result,
            "risk_level": item.risk_level, "approval_id": str(item.approval_id) if item.approval_id else None,
            "status": item.status, "idempotency_key": item.idempotency_key, "result": item.result_json,
            "error": item.error, "created_at": _iso(item.created_at),
        } for item in actions]
    return result


def list_traces(db: Session, merchant_id: uuid.UUID, *, offset: int = 0, limit: int = 25) -> tuple[list[dict], int]:
    query = db.query(AgentSession).filter(AgentSession.merchant_id == merchant_id)
    total = query.count()
    rows = query.order_by(AgentSession.started_at.desc()).offset(offset).limit(limit).all()
    return [_serialize_session(row, db=db) for row in rows], total


def get_trace(db: Session, merchant_id: uuid.UUID, session_id: uuid.UUID) -> dict | None:
    session = db.query(AgentSession).filter(
        AgentSession.id == session_id, AgentSession.merchant_id == merchant_id,
    ).one_or_none()
    return _serialize_session(session, include_trace=True, db=db) if session else None


def serialize_notification(row: Notification) -> dict:
    return {
        "id": str(row.id),
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "read_at": _iso(row.read_at),
        "created_at": _iso(row.created_at),
    }


def create_notification(
    db: Session, merchant_id: uuid.UUID, *, notification_type: str, title: str, body: str,
) -> Notification:
    notification = Notification(
        merchant_id=merchant_id, type=notification_type, title=title, body=body, created_at=datetime.now(UTC),
    )
    db.add(notification)
    return notification


def list_notifications(
    db: Session, merchant_id: uuid.UUID, *, unread_only: bool = False, limit: int = 50,
) -> tuple[list[dict], int]:
    query = db.query(Notification).filter(Notification.merchant_id == merchant_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    total = query.count()
    rows = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return [serialize_notification(row) for row in rows], total


def action_center(db: Session, merchant_id: uuid.UUID) -> dict:
    since = datetime.now(UTC) - timedelta(hours=24)
    pending_approvals = db.query(ApprovalRequest).filter(
        ApprovalRequest.merchant_id == merchant_id, ApprovalRequest.status == "pending",
    ).count()
    unread_notifications = db.query(Notification).filter(
        Notification.merchant_id == merchant_id, Notification.read_at.is_(None),
    ).count()
    failed_actions = db.query(AgentAction).join(
        AgentSession, AgentSession.id == AgentAction.session_id,
    ).filter(
        AgentSession.merchant_id == merchant_id, AgentAction.status == "failed",
        AgentAction.created_at >= since,
    ).count()
    blocked_actions = db.query(AgentAction).join(
        AgentSession, AgentSession.id == AgentAction.session_id,
    ).filter(
        AgentSession.merchant_id == merchant_id, AgentAction.status == "blocked",
        AgentAction.created_at >= since,
    ).count()
    recent_failures = db.query(AuditLog).filter(
        AuditLog.merchant_id == merchant_id, AuditLog.result.in_(("failed", "blocked")),
    ).order_by(AuditLog.created_at.desc()).limit(8).all()
    approvals = db.query(ApprovalRequest).filter(
        ApprovalRequest.merchant_id == merchant_id, ApprovalRequest.status == "pending",
    ).order_by(ApprovalRequest.created_at.desc()).limit(8).all()
    notifications, _ = list_notifications(db, merchant_id, unread_only=True, limit=8)
    return {
        "counts": {
            "pending_approvals": pending_approvals,
            "unread_notifications": unread_notifications,
            "failed_actions_24h": failed_actions,
            "blocked_actions_24h": blocked_actions,
        },
        "recent_failures": [serialize_audit(row) for row in recent_failures],
        "pending_approvals": [{
            "id": str(row.id), "action_code": row.action_code, "risk_level": row.risk_level,
            "campaign_id": str(row.campaign_id) if row.campaign_id else None,
            "created_at": _iso(row.created_at), "payload": row.payload_json,
        } for row in approvals],
        "notifications": notifications,
    }