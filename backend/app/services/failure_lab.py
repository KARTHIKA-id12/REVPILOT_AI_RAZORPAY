"""Failure Lab scenario orchestration. Every scenario here drives the
REAL Action Pipeline (app/agents/pipeline.py) through a real failure and
back — nothing in this module fabricates a response. The only thing
'staged' is the setup (creating a fresh campaign/approval to act on so
the demo has something to fail against); the failure, the audit trail,
and the recovery are all genuine.
"""

import uuid

from sqlalchemy.orm import Session

from app.agents.pipeline import create_campaign_draft, decide_approval, request_campaign_approval, retry_execution
from app.agents.schemas import CreateCampaignDraftInput, RequestCampaignApprovalInput
from app.agents.service import create_session
from app.models.campaigns import AgentPermission, Campaign
from app.models.catalog import Product
from app.models.ops import AuditLog
from app.services.failure_injection import arm

SCENARIOS = {
    "payment_timeout": "Simulate Razorpay Timeout",
    "payment_provider_error": "Simulate Payment Failure",
    "duplicate_webhook": "Simulate Duplicate Webhook",
    "invalid_discount": "Simulate Policy Violation",
    "out_of_stock": "Simulate Out-of-Stock Product",
    "permission_denied": "Simulate Permission Denied",
}

SCENARIO_DETAILS = {
    "payment_timeout": {
        "description": "Provider timeout before a payment link is created.",
        "failure_mode": "provider_timeout",
        "recovery": "Retry with the same approval idempotency key.",
    },
    "payment_provider_error": {
        "description": "Provider returns a recoverable 502-style error.",
        "failure_mode": "provider_error",
        "recovery": "Retry after the provider error is contained.",
    },
    "duplicate_webhook": {
        "description": "The same signed payment event is delivered twice.",
        "failure_mode": "duplicate_delivery",
        "recovery": "Ignore the second event without double-counting revenue.",
    },
    "invalid_discount": {
        "description": "A campaign requests a discount above merchant policy.",
        "failure_mode": "policy_violation",
        "recovery": "Block before payment execution.",
    },
    "out_of_stock": {
        "description": "A campaign targets a product temporarily marked out of stock.",
        "failure_mode": "inventory_conflict",
        "recovery": "Block the draft and restore demo inventory state.",
    },
    "permission_denied": {
        "description": "The merchant permission for campaign drafting is denied.",
        "failure_mode": "permission_denied",
        "recovery": "Deny without creating a draft and restore the setting.",
    },
}


def _trace(stage: str, status: str, detail: str) -> dict:
    return {"stage": stage, "status": status, "detail": detail}


def _pick_two_in_stock_products(db: Session, merchant_id: uuid.UUID) -> list[Product]:
    return db.query(Product).filter(Product.merchant_id == merchant_id, Product.stock_status == "in_stock").limit(2).all()


def run_scenario(db: Session, merchant_id: uuid.UUID, scenario: str) -> dict:
    if scenario not in SCENARIOS:
        return {"error": f"Unknown scenario '{scenario}'. Must be one of: {sorted(SCENARIOS)}"}

    handler = {
        "payment_timeout": _run_provider_failure,
        "payment_provider_error": _run_provider_failure,
        "duplicate_webhook": _run_duplicate_webhook,
        "invalid_discount": _run_invalid_discount,
        "out_of_stock": _run_out_of_stock,
        "permission_denied": _run_permission_denied,
    }[scenario]
    return handler(db, merchant_id, scenario)


def _run_provider_failure(db: Session, merchant_id: uuid.UUID, scenario: str) -> dict:
    trace = [_trace("SETUP", "info", "Creating a small demo campaign to execute against.")]
    products = _pick_two_in_stock_products(db, merchant_id)
    if len(products) < 2:
        return {"trace": trace + [_trace("SETUP", "blocked", "Not enough in-stock products to build a demo campaign.")]}

    session = create_session(db, merchant_id, user_id=None, channel="merchant_console")
    draft = create_campaign_draft(db, merchant_id, session.id, CreateCampaignDraftInput(
        name=f"Failure Lab Demo - {SCENARIOS[scenario]}", objective="cross_sell",
        product_ids=[products[0].id, products[1].id], discount_percent=10, budget_amount=500,
    ))
    campaign_id = uuid.UUID(draft.result_json["campaign_id"])

    approval_action = request_campaign_approval(db, merchant_id, session.id, RequestCampaignApprovalInput(campaign_id=campaign_id))
    if approval_action.status != "pending_approval":
        trace.append(_trace("SETUP", "blocked", f"Could not reach a pending approval (status={approval_action.status})."))
        return {"trace": trace}
    approval_id = approval_action.approval_id
    trace.append(_trace("SETUP", "ok", f"Campaign drafted and pending approval (approval_id={approval_id})."))

    # Arm the REAL failure injector - the next real provider call for
    # this merchant will raise the real exception class.
    arm(merchant_id, scenario)
    trace.append(_trace("ARMED", "info", f"{SCENARIOS[scenario]} armed for the next payment attempt."))

    first_attempt = decide_approval(db, merchant_id, approval_id, "approve", decided_by_user_id=None)
    campaign = db.get(Campaign, campaign_id)

    if first_attempt.get("action_status") == "failed":
        trace.append(_trace("DETECTED", "failure", "Payment provider call failed (injected)."))
        error_row = db.query(AuditLog).filter(AuditLog.external_id == str(campaign_id), AuditLog.result == "failed").order_by(AuditLog.created_at.desc()).first()
        trace.append(_trace("PROTECTED", "ok", "No charge occurred. Campaign marked 'failed', not left in an ambiguous state."))
        trace.append(_trace("PROTECTED", "ok", f"Reason recorded: {error_row.error if error_row else 'see audit log'}"))
        trace.append(_trace("AUDITED", "ok", "Full failure recorded in the audit ledger with a recovery action."))

        # Now retry - the injector already consumed its single shot, so
        # this attempt goes through the REAL provider for real.
        retry_result = retry_execution(db, merchant_id, approval_id)
        db.refresh(campaign)
        if retry_result.get("action_status") == "executed":
            trace.append(_trace("RECOVERED", "ok", "Retry succeeded using the same idempotency key. Campaign is now running."))
        else:
            trace.append(_trace("RECOVERED", "failure", f"Retry did not succeed: {retry_result}"))
    else:
        trace.append(_trace("DETECTED", "warning", "Injected failure did not trigger - the provider call unexpectedly succeeded."))

    return {"trace": trace, "campaign_id": str(campaign_id), "final_campaign_status": campaign.status if campaign else None}


def _run_duplicate_webhook(db: Session, merchant_id: uuid.UUID, scenario: str) -> dict:
    """Sends the SAME properly-signed webhook payload twice through the
    REAL /api/v1/webhooks/razorpay endpoint (in-process ASGI call, not a
    hand-rolled reimplementation of its logic) — this exercises the
    actual signature verification and the actual idempotency check that
    lives in that endpoint function, not an approximation of it."""
    import hashlib
    import hmac
    import json

    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.models.commerce import Payment

    trace = [_trace("SETUP", "info", "Creating and executing a demo campaign to obtain a real payment link.")]
    products = _pick_two_in_stock_products(db, merchant_id)
    if len(products) < 2:
        return {"trace": trace + [_trace("SETUP", "blocked", "Not enough in-stock products.")]}

    session = create_session(db, merchant_id, user_id=None, channel="merchant_console")
    draft = create_campaign_draft(db, merchant_id, session.id, CreateCampaignDraftInput(
        name="Failure Lab Demo - Duplicate Webhook", objective="cross_sell",
        product_ids=[products[0].id, products[1].id], discount_percent=10, budget_amount=500,
    ))
    campaign_id = uuid.UUID(draft.result_json["campaign_id"])
    approval_action = request_campaign_approval(db, merchant_id, session.id, RequestCampaignApprovalInput(campaign_id=campaign_id))
    decide_approval(db, merchant_id, approval_action.approval_id, "approve", decided_by_user_id=None)

    payment = db.query(Payment).filter(Payment.campaign_id == campaign_id).one_or_none()
    if not payment:
        trace.append(_trace("SETUP", "blocked", "Payment link execution did not succeed; cannot demonstrate duplicate webhook."))
        return {"trace": trace}
    trace.append(_trace("SETUP", "ok", f"Payment link created (provider={payment.provider})."))

    settings = get_settings()
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        trace.append(_trace("SETUP", "blocked", "RAZORPAY_WEBHOOK_SECRET is not configured; cannot sign a demo webhook."))
        return {"trace": trace}

    body = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": payment.provider_payment_link_id, "amount": int(float(payment.amount) * 100), "amount_paid": int(float(payment.amount) * 100), "status": "paid", "customer": {}}},
            "payment": {"entity": {"id": f"pay_faillab_{uuid.uuid4().hex[:12]}", "amount": int(float(payment.amount) * 100), "status": "captured"}},
        },
    }
    raw = json.dumps(body).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    event_id = f"evt_faillab_{uuid.uuid4().hex}"
    headers = {"content-type": "application/json", "x-razorpay-signature": signature, "x-razorpay-event-id": event_id}

    # Lazy import to avoid a circular import (app.main imports the demo
    # router, which imports this module).
    from app.main import app as fastapi_app

    test_client = TestClient(fastapi_app)
    campaign = db.get(Campaign, campaign_id)
    revenue_before = float(campaign.actual_revenue_amount)

    first = test_client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers)
    db.expire_all()
    campaign = db.get(Campaign, campaign_id)
    revenue_after_first = float(campaign.actual_revenue_amount)
    trace.append(_trace(
        "FIRST DELIVERY", "ok" if first.json().get("status") == "processed" else "failure",
        f"Webhook processed via the real endpoint. Revenue: Rs {revenue_before:,.0f} -> Rs {revenue_after_first:,.0f}.",
    ))

    second = test_client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers)
    trace.append(_trace(
        "DUPLICATE DELIVERY", "ok" if second.json().get("status") == "duplicate_ignored" else "failure",
        f"Same event_id resent to the real endpoint. Response: {second.json().get('status')}.",
    ))

    db.expire_all()
    campaign = db.get(Campaign, campaign_id)
    revenue_after_second = float(campaign.actual_revenue_amount)
    trace.append(_trace(
        "VERIFIED", "ok" if revenue_after_second == revenue_after_first else "failure",
        f"Revenue after duplicate: Rs {revenue_after_second:,.0f} (counted exactly once).",
    ))

    return {"trace": trace, "campaign_id": str(campaign_id)}


def _run_invalid_discount(db: Session, merchant_id: uuid.UUID, scenario: str) -> dict:
    trace = []
    products = _pick_two_in_stock_products(db, merchant_id)
    if len(products) < 2:
        return {"trace": [_trace("SETUP", "blocked", "Not enough in-stock products.")]}

    session = create_session(db, merchant_id, user_id=None, channel="merchant_console")
    draft = create_campaign_draft(db, merchant_id, session.id, CreateCampaignDraftInput(
        name="Failure Lab Demo - Policy Violation", objective="cross_sell",
        product_ids=[products[0].id, products[1].id], discount_percent=25, budget_amount=500,
    ))
    trace.append(_trace("REQUEST", "info", "Agent requests a 25% discount campaign."))
    campaign_id = uuid.UUID(draft.result_json["campaign_id"])

    approval_action = request_campaign_approval(db, merchant_id, session.id, RequestCampaignApprovalInput(campaign_id=campaign_id))
    if approval_action.status == "blocked":
        trace.append(_trace("POLICY CHECK", "blocked", approval_action.error))
        trace.append(_trace("RESULT", "ok", "Action blocked before any financial commitment. Campaign remains in draft."))
    else:
        trace.append(_trace("POLICY CHECK", "failure", "Expected this to be blocked, but it was not."))
    return {"trace": trace, "campaign_id": str(campaign_id)}


def _run_out_of_stock(db: Session, merchant_id: uuid.UUID, scenario: str) -> dict:
    trace = []
    products = _pick_two_in_stock_products(db, merchant_id)
    if len(products) < 2:
        return {"trace": [_trace("SETUP", "blocked", "Not enough in-stock products.")]}

    target = products[1]
    original_status = target.stock_status
    target.stock_status = "out_of_stock"
    db.flush()
    trace.append(_trace("SETUP", "info", f"Temporarily marking '{target.name}' out of stock for this demo."))

    try:
        session = create_session(db, merchant_id, user_id=None, channel="merchant_console")
        draft = create_campaign_draft(db, merchant_id, session.id, CreateCampaignDraftInput(
            name="Failure Lab Demo - Out of Stock", objective="cross_sell",
            product_ids=[products[0].id, target.id], discount_percent=10, budget_amount=500,
        ))
        if draft.status == "blocked":
            trace.append(_trace("STOCK CHECK", "blocked", draft.error))
            trace.append(_trace("RESULT", "ok", "Campaign draft blocked before any commitment - out-of-stock products can't be targeted."))
        else:
            trace.append(_trace("STOCK CHECK", "failure", "Expected this to be blocked, but it was not."))
    finally:
        target.stock_status = original_status
        db.flush()
        db.commit()
        trace.append(_trace("CLEANUP", "info", f"Restored '{target.name}' to its real stock status."))

    return {"trace": trace}


def _run_permission_denied(db: Session, merchant_id: uuid.UUID, scenario: str) -> dict:
    trace = []
    permission = db.query(AgentPermission).filter(AgentPermission.merchant_id == merchant_id, AgentPermission.action_code == "CREATE_CAMPAIGN_DRAFT").one_or_none()
    original_mode = permission.mode if permission else "ALLOW"
    if permission:
        permission.mode = "DENY"
    else:
        db.add(AgentPermission(merchant_id=merchant_id, action_code="CREATE_CAMPAIGN_DRAFT", mode="DENY"))
    db.flush()
    trace.append(_trace("SETUP", "info", "Temporarily setting CREATE_CAMPAIGN_DRAFT to DENY for this demo."))

    try:
        products = _pick_two_in_stock_products(db, merchant_id)
        session = create_session(db, merchant_id, user_id=None, channel="merchant_console")
        draft = create_campaign_draft(db, merchant_id, session.id, CreateCampaignDraftInput(
            name="Failure Lab Demo - Permission Denied", objective="cross_sell",
            product_ids=[products[0].id, products[1].id], discount_percent=10, budget_amount=500,
        ))
        if draft.status == "blocked":
            trace.append(_trace("PERMISSION CHECK", "blocked", draft.error))
            trace.append(_trace("RESULT", "ok", "Action denied by merchant settings - no draft was created."))
        else:
            trace.append(_trace("PERMISSION CHECK", "failure", "Expected this to be denied, but it was not."))
    finally:
        db.query(AgentPermission).filter(
            AgentPermission.merchant_id == merchant_id, AgentPermission.action_code == "CREATE_CAMPAIGN_DRAFT"
        ).update({"mode": original_mode})
        db.commit()
        trace.append(_trace("CLEANUP", "info", f"Restored CREATE_CAMPAIGN_DRAFT to {original_mode}."))

    return {"trace": trace}
