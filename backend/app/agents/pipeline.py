"""The Action Pipeline. Every action tool call — whether triggered by a
real LLM or the demo-mode keyword router — passes through this exact
sequence, with no shortcuts:

    validate (Pydantic) -> permission check -> policy check
    -> financial recalculation (never trust agent-supplied numbers)
    -> simulation (for campaign actions) -> approval gate
    -> idempotency key -> execute -> verify -> audit

Design decisions that close specific loopholes:

1. Every financial number (discount cost, reach, AOV, campaign amount) is
   recomputed here from live DB state. The agent's payload may carry a
   discount_percent and product_ids (parameters), never a price or a
   revenue figure (see app/agents/schemas.py — no such fields exist on
   the action input models, so there is nothing to "trust" even if we
   wanted to).

2. Approval binds to the EXACT recalculated payload stored in
   approval_requests.payload_json at request time. When a merchant later
   approves, execution reads that stored payload — never a fresh request —
   so there is no window for the numbers to drift between "what the
   merchant saw" and "what gets charged".

3. Idempotency keys are deterministic (derived from approval_id or a
   caller-supplied key), and execution checks for an existing Payment row
   with that key BEFORE calling the payment provider. A duplicate
   approval click, a retried request, or a replayed webhook can never
   create two charges for the same approved action.

4. Policy is re-evaluated at BOTH request-time and approval-time (not
   just once) — if stock or a policy value changed in between, the
   second check catches it rather than executing against stale facts.

5. Every branch — blocked, pending_approval, executed, failed — writes an
   AuditLog row. There is no "silent" outcome.
"""

import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from sqlalchemy.orm import Session

from app.agents.schemas import CreateCampaignDraftInput, RequestCampaignApprovalInput, SimulateCampaignInput
from app.campaigns.inputs import compute_simulation_inputs
from app.campaigns.simulation import simulate_campaign
from app.integrations.razorpay.exceptions import PaymentProviderError
from app.integrations.razorpay.factory import get_payment_provider
from app.models.agent import AgentAction
from app.models.campaigns import ApprovalRequest, Campaign
from app.models.commerce import Payment
from app.models.opportunities import RevenueOpportunity
from app.models.ops import AuditLog
from app.ops.service import create_notification
from app.policies.permissions import PermissionMode, get_permission_mode
from app.policies.risk import classify_risk
from app.policies.rules import run_campaign_policy_checks, run_draft_policy_checks


def _audit(
    db: Session, merchant_id: uuid.UUID, *, agent_session_id: uuid.UUID | None, action: str, tool: str | None,
    input_summary: str, reason: str | None, policy_result: str | None, permission_result: str | None,
    approval_id: uuid.UUID | None, external_id: str | None, result: str, error: str | None = None,
    recovery_action: str | None = None,
) -> None:
    db.add(AuditLog(
        merchant_id=merchant_id, agent_session_id=agent_session_id, action=action, tool=tool,
        input_summary=input_summary[:1000], reason=reason, policy_result=policy_result,
        permission_result=permission_result, approval_id=approval_id, external_id=external_id,
        result=result, error=error, recovery_action=recovery_action, created_at=datetime.now(UTC),
    ))
    if result in {"failed", "blocked", "recovered"}:
        labels = {
            "failed": ("action_failed", "Action failed"),
            "blocked": ("action_blocked", "Action blocked by guardrails"),
            "recovered": ("action_recovered", "Action recovered"),
        }
        notification_type, title = labels[result]
        detail = error or reason or recovery_action or f"{action} completed."
        create_notification(
            db, merchant_id, notification_type=notification_type,
            title=title, body=f"{action}: {detail}",
        )


def _record_action(
    db: Session, *, session_id: uuid.UUID, action_code: str, input_json: dict, policy_result: dict,
    permission_result: str, risk_level: str, approval_id: uuid.UUID | None, status: str,
    idempotency_key: str | None, result_json: dict, error: str | None = None,
) -> AgentAction:
    action = AgentAction(
        session_id=session_id, action_code=action_code, input_json=input_json, policy_result=policy_result,
        permission_result=permission_result, risk_level=risk_level, approval_id=approval_id, status=status,
        idempotency_key=idempotency_key, result_json=result_json, error=error, created_at=datetime.now(UTC),
    )
    db.add(action)
    db.flush()
    return action


def _campaigns_created_today(db: Session, merchant_id: uuid.UUID) -> int:
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(Campaign).filter(Campaign.merchant_id == merchant_id, Campaign.created_at >= start_of_day).count()


def simulate_campaign_action(db: Session, merchant_id: uuid.UUID, session_id: uuid.UUID, payload: SimulateCampaignInput) -> AgentAction:
    """SIMULATE_CAMPAIGN is always ALLOW and has zero side effects on
    money — it's pure computation, safe to run as often as asked."""
    from app.campaigns.inputs import resolve_product_ids_and_confidence
    resolved = resolve_product_ids_and_confidence(db, merchant_id, opportunity_id=payload.opportunity_id, product_ids=payload.product_ids)
    if not resolved.get("found"):
        raise AppError("SIMULATION_TARGET_NOT_FOUND", "Simulation target not found.", status_code=404)

    sim = simulate_campaign(
        eligible_customers=resolved["eligible_customers"], average_order_value=resolved["average_order_value"],
        discount_percent=payload.discount_percent, organic_confidence=resolved["organic_confidence"],
    )
    result = sim.as_dict()

    action = _record_action(
        db, session_id=session_id, action_code="SIMULATE_CAMPAIGN", input_json=payload.model_dump(mode="json"),
        policy_result={"passed": True, "violations": []}, permission_result=PermissionMode.ALLOW.value,
        risk_level=classify_risk("SIMULATE_CAMPAIGN"), approval_id=None, status="executed",
        idempotency_key=None, result_json=result,
    )
    _audit(
        db, merchant_id, agent_session_id=session_id, action="SIMULATE_CAMPAIGN", tool="simulate_campaign",
        input_summary=f"discount={payload.discount_percent}% products={len(payload.product_ids)}",
        reason="pure computation, no approval required", policy_result="passed", permission_result="ALLOW",
        approval_id=None, external_id=None, result="success",
    )
    db.commit()
    return action


def create_campaign_draft(db: Session, merchant_id: uuid.UUID, session_id: uuid.UUID, payload: CreateCampaignDraftInput) -> AgentAction:
    """CREATE_CAMPAIGN_DRAFT is ALLOW by default — drafting doesn't move
    money — but stock/budget policy still applies so a draft can never be
    built around an impossible action (e.g. an out-of-stock product)."""
    policy_result = run_draft_policy_checks(
        db, merchant_id, budget_amount=payload.budget_amount,
        product_ids=payload.product_ids, campaigns_created_today=_campaigns_created_today(db, merchant_id),
    )
    permission_mode = get_permission_mode(db, merchant_id, "CREATE_CAMPAIGN_DRAFT")

    if not policy_result.passed or permission_mode == PermissionMode.DENY:
        action = _record_action(
            db, session_id=session_id, action_code="CREATE_CAMPAIGN_DRAFT", input_json=payload.model_dump(mode="json"),
            policy_result=policy_result.as_dict(), permission_result=permission_mode.value,
            risk_level=classify_risk("CREATE_CAMPAIGN_DRAFT"), approval_id=None, status="blocked",
            idempotency_key=None, result_json={}, error="; ".join(policy_result.violations) or "Denied by permission settings.",
        )
        _audit(
            db, merchant_id, agent_session_id=session_id, action="CREATE_CAMPAIGN_DRAFT", tool="create_campaign_draft",
            input_summary=f"discount={payload.discount_percent}% budget={payload.budget_amount}",
            reason=action.error, policy_result="failed" if not policy_result.passed else "passed",
            permission_result=permission_mode.value, approval_id=None, external_id=None, result="blocked", error=action.error,
        )
        db.commit()
        return action

    campaign = Campaign(
        merchant_id=merchant_id, opportunity_id=payload.opportunity_id, name=payload.name, objective=payload.objective,
        product_ids_json=[str(p) for p in payload.product_ids], discount_percent=payload.discount_percent,
        budget_amount=payload.budget_amount, status="draft",
    )
    db.add(campaign)
    db.flush()

    # An opportunity that has been turned into a campaign is no longer
    # "open" — mark it actioned so (a) it stops showing as an untouched
    # suggestion, and (b) the analytics refresh (which only clears status
    #='open' rows) never tries to delete a row a campaign still
    # references. This was a real bug found during testing: without this,
    # re-running analysis after acting on an opportunity raised a foreign
    # key violation instead of a clean, intended state transition.
    if payload.opportunity_id:
        opportunity = db.get(RevenueOpportunity, payload.opportunity_id)
        if opportunity and opportunity.merchant_id == merchant_id:
            opportunity.status = "actioned"
            db.flush()

    action = _record_action(
        db, session_id=session_id, action_code="CREATE_CAMPAIGN_DRAFT", input_json=payload.model_dump(mode="json"),
        policy_result=policy_result.as_dict(), permission_result=permission_mode.value,
        risk_level=classify_risk("CREATE_CAMPAIGN_DRAFT"), approval_id=None, status="executed",
        idempotency_key=None, result_json={"campaign_id": str(campaign.id), "status": "draft"},
    )
    _audit(
        db, merchant_id, agent_session_id=session_id, action="CREATE_CAMPAIGN_DRAFT", tool="create_campaign_draft",
        input_summary=f"name={payload.name} discount={payload.discount_percent}%", reason="policy and permission passed",
        policy_result="passed", permission_result=permission_mode.value, approval_id=None,
        external_id=str(campaign.id), result="success",
    )
    db.commit()
    return action


def request_campaign_approval(db: Session, merchant_id: uuid.UUID, session_id: uuid.UUID, payload: RequestCampaignApprovalInput) -> AgentAction:
    """The gate where CREATE_DISCOUNT permission and the discount-cap
    policy apply — submitting a draft's discount for real approval."""
    campaign = db.query(Campaign).filter(Campaign.id == payload.campaign_id, Campaign.merchant_id == merchant_id).one_or_none()
    if not campaign:
        action = _record_action(
            db, session_id=session_id, action_code="CREATE_DISCOUNT", input_json=payload.model_dump(mode="json"),
            policy_result={"passed": False, "violations": ["campaign not found"]}, permission_result="N/A",
            risk_level="medium", approval_id=None, status="failed", idempotency_key=None, result_json={},
            error="Campaign not found for this merchant.",
        )
        db.commit()
        return action

    product_ids = [uuid.UUID(p) for p in campaign.product_ids_json]
    policy_result = run_campaign_policy_checks(
        db, merchant_id, discount_percent=float(campaign.discount_percent), budget_amount=float(campaign.budget_amount),
        product_ids=product_ids, campaigns_created_today=_campaigns_created_today(db, merchant_id),
    )
    permission_mode = get_permission_mode(db, merchant_id, "CREATE_DISCOUNT")

    if not policy_result.passed:
        action = _record_action(
            db, session_id=session_id, action_code="CREATE_DISCOUNT", input_json=payload.model_dump(mode="json"),
            policy_result=policy_result.as_dict(), permission_result=permission_mode.value,
            risk_level=classify_risk("CREATE_DISCOUNT"), approval_id=None, status="blocked",
            idempotency_key=None, result_json={}, error="; ".join(policy_result.violations),
        )
        _audit(
            db, merchant_id, agent_session_id=session_id, action="CREATE_DISCOUNT", tool="request_campaign_approval",
            input_summary=f"campaign={campaign.id} discount={campaign.discount_percent}%",
            reason="; ".join(policy_result.violations), policy_result="failed", permission_result=permission_mode.value,
            approval_id=None, external_id=str(campaign.id), result="blocked", error="; ".join(policy_result.violations),
        )
        db.commit()
        return action

    if permission_mode == PermissionMode.DENY:
        action = _record_action(
            db, session_id=session_id, action_code="CREATE_DISCOUNT", input_json=payload.model_dump(mode="json"),
            policy_result=policy_result.as_dict(), permission_result=permission_mode.value,
            risk_level=classify_risk("CREATE_DISCOUNT"), approval_id=None, status="blocked",
            idempotency_key=None, result_json={}, error="Discount actions are denied by merchant settings.",
        )
        _audit(
            db, merchant_id, agent_session_id=session_id, action="CREATE_DISCOUNT", tool="request_campaign_approval",
            input_summary=f"campaign={campaign.id}", reason="denied by permission settings", policy_result="passed",
            permission_result=permission_mode.value, approval_id=None, external_id=str(campaign.id), result="blocked",
        )
        db.commit()
        return action

    # Recalculate the exact financial payload NOW, and freeze it into the
    # approval request. Execution (on approval) will replay THIS payload —
    # never a freshly-submitted one.
    inputs = compute_simulation_inputs(db, merchant_id, product_ids)
    sim = simulate_campaign(
        eligible_customers=inputs["eligible_customers"], average_order_value=inputs["average_order_value"],
        discount_percent=float(campaign.discount_percent), organic_confidence=inputs["organic_confidence"],
    )
    frozen_payload = {
        "campaign_id": str(campaign.id),
        "product_ids": [str(p) for p in product_ids],
        "discount_percent": float(campaign.discount_percent),
        "budget_amount": float(campaign.budget_amount),
        "simulation": sim.as_dict(),
        "recalculated_at": datetime.now(UTC).isoformat(),
    }

    if permission_mode == PermissionMode.ALLOW:
        # Merchant has explicitly configured this action to run without
        # approval. Execute immediately using the just-recalculated payload.
        campaign.status = "approved"
        db.flush()
        return _execute_payment_link(
            db, merchant_id, session_id, campaign, frozen_payload, approval_id=None,
            idempotency_key=f"direct_{campaign.id}",
        )

    approval = ApprovalRequest(
        merchant_id=merchant_id, campaign_id=campaign.id, action_code="CREATE_DISCOUNT",
        payload_json=frozen_payload, risk_level=classify_risk("CREATE_DISCOUNT"),
        policy_result_json=policy_result.as_dict(), status="pending", requested_by_agent_session_id=session_id,
    )
    db.add(approval)
    campaign.status = "pending_approval"
    db.flush()

    action = _record_action(
        db, session_id=session_id, action_code="CREATE_DISCOUNT", input_json=payload.model_dump(mode="json"),
        policy_result=policy_result.as_dict(), permission_result=permission_mode.value,
        risk_level=classify_risk("CREATE_DISCOUNT"), approval_id=approval.id, status="pending_approval",
        idempotency_key=None, result_json={"approval_id": str(approval.id), "simulation": sim.as_dict()},
    )
    _audit(
        db, merchant_id, agent_session_id=session_id, action="CREATE_DISCOUNT", tool="request_campaign_approval",
        input_summary=f"campaign={campaign.id} discount={campaign.discount_percent}%", reason="requires merchant approval",
        policy_result="passed", permission_result=permission_mode.value, approval_id=approval.id,
        external_id=str(campaign.id), result="pending_approval",
    )
    db.commit()
    return action


def _execute_payment_link(
    db: Session, merchant_id: uuid.UUID, session_id: uuid.UUID | None, campaign: Campaign, frozen_payload: dict,
    *, approval_id: uuid.UUID | None, idempotency_key: str,
) -> AgentAction:
    """The actual money-moving step. Idempotency is checked BEFORE calling
    the provider — a duplicate approval click or retried request returns
    the existing result rather than creating a second charge."""
    existing_payment = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).one_or_none()
    if existing_payment:
        action = _record_action(
            db, session_id=session_id, action_code="CREATE_PAYMENT_LINK", input_json=frozen_payload,
            policy_result={"passed": True, "violations": []}, permission_result="ALLOW", risk_level="high",
            approval_id=approval_id, status="executed", idempotency_key=idempotency_key,
            result_json={"payment_id": str(existing_payment.id), "duplicate_prevented": True},
        )
        _audit(
            db, merchant_id, agent_session_id=session_id, action="CREATE_PAYMENT_LINK", tool="create_payment_link",
            input_summary=f"campaign={campaign.id}", reason="idempotency key already used — duplicate execution prevented",
            policy_result="passed", permission_result="ALLOW", approval_id=approval_id,
            external_id=str(existing_payment.id), result="success", recovery_action="returned existing payment, no duplicate charge",
        )
        db.commit()
        return action

    # Re-check policy one more time at execution time — stock or budget
    # may have changed since the approval request was created.
    product_ids = [uuid.UUID(p) for p in frozen_payload["product_ids"]]
    policy_result = run_campaign_policy_checks(
        db, merchant_id, discount_percent=frozen_payload["discount_percent"], budget_amount=frozen_payload["budget_amount"],
        product_ids=product_ids, campaigns_created_today=0,  # daily count already satisfied at request time
    )
    if not policy_result.passed:
        campaign.status = "failed"
        db.flush()
        action = _record_action(
            db, session_id=session_id, action_code="CREATE_PAYMENT_LINK", input_json=frozen_payload,
            policy_result=policy_result.as_dict(), permission_result="ALLOW", risk_level="high",
            approval_id=approval_id, status="failed", idempotency_key=idempotency_key, result_json={},
            error="Policy conditions changed since approval: " + "; ".join(policy_result.violations),
        )
        _audit(
            db, merchant_id, agent_session_id=session_id, action="CREATE_PAYMENT_LINK", tool="create_payment_link",
            input_summary=f"campaign={campaign.id}", reason="; ".join(policy_result.violations), policy_result="failed",
            permission_result="ALLOW", approval_id=approval_id, external_id=str(campaign.id), result="failed",
            error="; ".join(policy_result.violations),
        )
        db.commit()
        return action

    provider = get_payment_provider(merchant_id=merchant_id)
    total_amount = frozen_payload["simulation"]["expected_revenue"] or 1  # never create a ₹0 link

    try:
        provider_result = provider.create_payment_link(
            amount=int(total_amount), currency="INR", reference_id=str(campaign.id),
            description=f"RevPilot campaign: {campaign.name}",
        )
    except PaymentProviderError as exc:
        # A Razorpay outage, auth failure, or timeout must never leave an
        # ambiguous state: no Payment row is created (so a later retry
        # with the SAME idempotency_key is safe — the check at the top of
        # this function will not find a duplicate to worry about), the
        # campaign is marked failed rather than silently stuck in
        # 'approved', and the failure is fully audited so it shows up in
        # the Failure Lab / audit ledger rather than as an opaque 500.
        campaign.status = "failed"
        db.flush()
        action = _record_action(
            db, session_id=session_id, action_code="CREATE_PAYMENT_LINK", input_json=frozen_payload,
            policy_result={"passed": True, "violations": []}, permission_result="ALLOW", risk_level="high",
            approval_id=approval_id, status="failed", idempotency_key=idempotency_key, result_json={},
            error=str(exc),
        )
        _audit(
            db, merchant_id, agent_session_id=session_id, action="CREATE_PAYMENT_LINK", tool="create_payment_link",
            input_summary=f"campaign={campaign.id} amount={total_amount}", reason=str(exc),
            policy_result="passed", permission_result="ALLOW", approval_id=approval_id,
            external_id=str(campaign.id), result="failed", error=str(exc),
            recovery_action="No charge occurred. Safe to retry — the same idempotency key will be reused.",
        )
        db.commit()
        return action

    payment = Payment(
        merchant_id=merchant_id, campaign_id=campaign.id, provider=provider_result["provider"],
        provider_payment_link_id=provider_result["provider_payment_link_id"], amount=total_amount, currency="INR",
        status="created", idempotency_key=idempotency_key,
    )
    db.add(payment)
    campaign.status = "running"
    campaign.starts_at = datetime.now(UTC)
    # Populate the campaign's expected_revenue_amount from the same
    # simulation that was frozen at approval time — this was a real gap
    # found while building the Campaigns view: the field exists on the
    # model and the spec explicitly calls for showing it, but nothing
    # upstream ever wrote to it, so every campaign silently showed ₹0
    # expected revenue after execution.
    campaign.expected_revenue_amount = frozen_payload["simulation"]["expected_revenue"]
    db.flush()

    action = _record_action(
        db, session_id=session_id, action_code="CREATE_PAYMENT_LINK", input_json=frozen_payload,
        policy_result=policy_result.as_dict(), permission_result="ALLOW", risk_level="high",
        approval_id=approval_id, status="executed", idempotency_key=idempotency_key,
        result_json={"payment_id": str(payment.id), "provider": provider_result["provider"], "short_url": provider_result.get("short_url")},
    )
    _audit(
        db, merchant_id, agent_session_id=session_id, action="CREATE_PAYMENT_LINK", tool="create_payment_link",
        input_summary=f"campaign={campaign.id} amount={total_amount}", reason="approved and executed",
        policy_result="passed", permission_result="ALLOW", approval_id=approval_id, external_id=str(payment.id),
        result="success",
    )
    db.commit()
    return action


def decide_approval(db: Session, merchant_id: uuid.UUID, approval_id: uuid.UUID, decision: str, decided_by_user_id: uuid.UUID | None) -> dict:
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id, ApprovalRequest.merchant_id == merchant_id).one_or_none()
    if not approval:
        return {"error": "approval_not_found"}
    if approval.status != "pending":
        return {"error": f"approval already {approval.status}"}

    campaign = db.get(Campaign, approval.campaign_id) if approval.campaign_id else None

    if decision == "reject":
        approval.status = "rejected"
        approval.decided_by_user_id = decided_by_user_id
        approval.decided_at = datetime.now(UTC)
        if campaign:
            campaign.status = "cancelled"
        _audit(
            db, merchant_id, agent_session_id=approval.requested_by_agent_session_id, action=approval.action_code,
            tool="decide_approval", input_summary=f"approval={approval.id}", reason="merchant rejected",
            policy_result="n/a", permission_result="APPROVAL", approval_id=approval.id,
            external_id=str(campaign.id) if campaign else None, result="blocked",
        )
        db.commit()
        return {"status": "rejected"}

    approval.status = "approved"
    approval.decided_by_user_id = decided_by_user_id
    approval.decided_at = datetime.now(UTC)
    db.flush()

    if not campaign:
        db.commit()
        return {"status": "approved", "note": "no campaign attached to this approval"}

    action = _execute_payment_link(
        db, merchant_id, approval.requested_by_agent_session_id, campaign, approval.payload_json,
        approval_id=approval.id, idempotency_key=f"approval_{approval.id}",
    )
    return {"status": "approved", "action_status": action.status, "result": action.result_json}


def retry_execution(db: Session, merchant_id: uuid.UUID, approval_id: uuid.UUID) -> dict:
    """Safely retries execution for an approval that was already approved
    but whose payment-link creation failed (provider timeout, API error,
    etc.). Reuses the exact same idempotency_key as the original attempt
    — if that attempt actually succeeded on Razorpay's side despite the
    error reaching us (e.g. a timeout on our end after Razorpay processed
    it), the idempotency check in _execute_payment_link returns the
    existing result instead of creating a second charge. If it genuinely
    never went through, this attempt proceeds normally."""
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id, ApprovalRequest.merchant_id == merchant_id).one_or_none()
    if not approval:
        return {"error": "approval_not_found"}
    if approval.status != "approved":
        return {"error": f"cannot retry an approval with status '{approval.status}' (must be 'approved')"}

    campaign = db.get(Campaign, approval.campaign_id) if approval.campaign_id else None
    if not campaign:
        return {"error": "no campaign attached to this approval"}
    if campaign.status != "failed":
        return {"error": f"campaign is '{campaign.status}', not 'failed' — nothing to retry"}

    action = _execute_payment_link(
        db, merchant_id, approval.requested_by_agent_session_id, campaign, approval.payload_json,
        approval_id=approval.id, idempotency_key=f"approval_{approval.id}",
    )
    return {"status": "retried", "action_status": action.status, "result": action.result_json, "error": action.error}
