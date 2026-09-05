"""Agent session orchestration. Handles session lifecycle and routes each
user message to either a read tool (grounded DB answer) or an action tool
(routed through the Action Pipeline).

Intent extraction has two implementations behind one interface,
`_classify_intent()`:

  - Keyword router (`_classify_intent_by_keyword`): deterministic,
    zero-cost, always available. Used when AI_PROVIDER=mock (the default)
    or as the resilience fallback if the real provider fails.
  - Free open-model router (`_classify_intent_with_llm`): calls a real
    LLM via app.agents.providers.get_ai_provider() -- currently Hugging
    Face's Inference Providers router, a free tier over open-weight
    models (see app/agents/huggingface_provider.py), not a paid API.

Whichever one runs, the output is the SAME small, closed-set structured
intent (validated by app.agents.intent_schema.ParsedIntent), and it feeds
into the exact same tool dispatch and Action Pipeline below. The model
is never trusted with a product ID, a customer ID, or a dollar amount --
only a named intent and, at most, a bounded discount percentage that
gets independently re-validated and re-priced by deterministic code
before anything happens. See docs/system-overview.md Section 1.
"""

import json
import re
import time
import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.pipeline import create_campaign_draft, request_campaign_approval, simulate_campaign_action
from app.agents.read_tools import get_product_details, get_revenue_opportunities
from app.agents.schemas import CreateCampaignDraftInput, RequestCampaignApprovalInput, SimulateCampaignInput
from app.core.config import get_settings
from app.models.agent import AgentMessage, AgentSession, AgentToolCall
from app.models.catalog import Product
from app.models.opportunities import RevenueOpportunity


def create_session(db: Session, merchant_id: uuid.UUID, user_id: uuid.UUID | None, channel: str = "merchant_console") -> AgentSession:
    session = AgentSession(merchant_id=merchant_id, user_id=user_id, channel=channel, status="active", started_at=datetime.now(UTC))
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _log_message(db: Session, session_id: uuid.UUID, role: str, content: str) -> None:
    db.add(AgentMessage(session_id=session_id, role=role, content=content, created_at=datetime.now(UTC)))
    db.commit()


def _log_tool_call(db: Session, session_id: uuid.UUID, tool_name: str, input_json: dict, output_json: dict, status: str, latency_ms: int = 0) -> None:
    db.add(AgentToolCall(
        session_id=session_id, tool_name=tool_name, input_json=input_json, output_json=output_json,
        latency_ms=latency_ms, status=status, created_at=datetime.now(UTC),
    ))
    db.commit()


# --- Intent extraction --------------------------------------------------

_DISCOUNT_PATTERN = re.compile(r"(\d+)\s*%")

_INTENT_CLASSIFIER_SYSTEM_PROMPT = (
    "You are the intent classifier for a merchant revenue-agent console called RevPilot. "
    "You never see real data and you never decide amounts -- you only classify what the "
    "merchant is asking for. Read the merchant's message and respond with ONLY a single "
    "JSON object (no prose, no markdown fences) with exactly these keys:\n"
    '  "intent": one of "CREATE_CAMPAIGN_DRAFT", "VIEW_OPPORTUNITIES", "VIEW_REVENUE", '
    '"VIEW_SEGMENTS", "SIMULATE_CAMPAIGN", "PRODUCT_LOOKUP", "UNKNOWN"\n'
    '  "discount_percent": a number between 0 and 100 if the message mentions a specific '
    'discount level, otherwise null\n'
    "Pick UNKNOWN if the message does not clearly match any other intent -- never invent "
    "an intent outside this list, and never include any field except these two."
)


def _extract_discount(lowered: str) -> float | None:
    match = _DISCOUNT_PATTERN.search(lowered)
    return float(match.group(1)) if match else None


def _classify_intent_by_keyword(lowered: str) -> dict:
    """Deterministic fallback / default. Exactly reproduces the keyword
    rules this router has always used, just factored out so the LLM path
    can share the same downstream dispatch below."""
    if "goal" in lowered or "analyze" in lowered or "analyse" in lowered or "grow" in lowered:
        return {"name": "ANALYZE_GOAL", "discount_percent": None}
    if "create" in lowered and "campaign" in lowered:
        return {"name": "CREATE_CAMPAIGN_DRAFT", "discount_percent": _extract_discount(lowered)}
    if "opportunit" in lowered:
        return {"name": "VIEW_OPPORTUNITIES", "discount_percent": None}
    if "revenue" in lowered or "how much" in lowered:
        return {"name": "VIEW_REVENUE", "discount_percent": None}
    if "segment" in lowered or "at risk" in lowered or "at-risk" in lowered:
        return {"name": "VIEW_SEGMENTS", "discount_percent": None}
    if ("simulate" in lowered or "what if" in lowered or "what happens if" in lowered) and _DISCOUNT_PATTERN.search(lowered):
        return {"name": "SIMULATE_CAMPAIGN", "discount_percent": _extract_discount(lowered)}
    if "price" in lowered or "product" in lowered:
        return {"name": "PRODUCT_LOOKUP", "discount_percent": None}
    return {"name": "UNKNOWN", "discount_percent": None}


def _classify_intent_with_llm(db: Session, session_id: uuid.UUID, user_text: str) -> dict | None:
    """Returns a validated {"name", "discount_percent"} dict from a real
    LLM call, or None on ANY failure (network error, timeout, malformed
    JSON, an intent name outside the closed set, an out-of-range
    discount). None means "fall back to the keyword router" -- this is a
    deliberate resilience choice: a flaky free-tier inference call should
    degrade the conversation, never break it. Every attempt (success or
    failure) is logged as a real AgentToolCall row, visible in the Agent
    Control Room / audit ledger."""
    from app.agents.intent_schema import ParsedIntent
    from app.agents.providers import get_ai_provider

    started = time.monotonic()
    try:
        provider = get_ai_provider()
        raw = provider.complete(
            system=_INTENT_CLASSIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
            response_schema={"type": "object"},
        )
        parsed = ParsedIntent.model_validate(json.loads(raw))
    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        _log_tool_call(
            db, session_id, "llm_intent_classify", {"text": user_text},
            {"error": f"{type(exc).__name__}: {exc}"}, "error",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return None
    except Exception as exc:  # noqa: BLE001 -- provider network/HTTP errors surface as AppError; never let a flaky free-tier call crash the chat
        _log_tool_call(
            db, session_id, "llm_intent_classify", {"text": user_text},
            {"error": f"{type(exc).__name__}: {exc}"}, "error",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return None

    _log_tool_call(
        db, session_id, "llm_intent_classify", {"text": user_text}, parsed.model_dump(), "ok",
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return {"name": parsed.intent, "discount_percent": parsed.discount_percent}


def _classify_intent(db: Session, session_id: uuid.UUID, user_text: str, lowered: str) -> dict:
    settings = get_settings()
    if settings.AI_PROVIDER != "mock" and settings.AI_API_KEY:
        llm_result = _classify_intent_with_llm(db, session_id, user_text)
        if llm_result is not None:
            return llm_result
    return _classify_intent_by_keyword(lowered)


# --- Message handling / tool dispatch ------------------------------------
# Everything below is provider-agnostic: it only ever sees the small,
# closed-set `intent` dict from _classify_intent() above, never raw model
# output. Financial values (discount, budget, revenue) are always
# recomputed by the deterministic Action Pipeline / analytics modules,
# regardless of which router proposed the intent.

def handle_message(db: Session, session: AgentSession, merchant_id: uuid.UUID, user_text: str) -> dict:
    _log_message(db, session.id, "user", user_text)
    lowered = user_text.lower()

    intent = _classify_intent(db, session.id, user_text, lowered)
    name = intent["name"]
    discount = intent.get("discount_percent")

    if name == "ANALYZE_GOAL":
        opp_result = get_revenue_opportunities(db, merchant_id, limit=1)
        if not opp_result.get("found"):
            reply = "I analyzed your data, but I couldn't find any immediate revenue opportunities right now."
        else:
            top = opp_result["opportunities"][0]
            reply = (
                f"I've analyzed your commerce data. Your top opportunity is a {top['type']} campaign "
                f"targeting {top['reach_count']} eligible customers. "
                f"Expected incremental revenue is Rs. {top['estimated_revenue_amount']:,.0f} with {top['confidence']}% confidence. "
                f"Based on our closed loop learning from past campaigns, this type of cross-sell performs well for your merchant profile. "
                f"I recommend simulating a 10% discount on this. Shall I create a draft campaign?"
            )
        _log_message(db, session.id, "assistant", reply)
        return {"reply": reply, "intent": "ANALYZE_GOAL", "tool_result": opp_result}

    if name == "CREATE_CAMPAIGN_DRAFT":
        import re
        top = None
        uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", lowered)
        if uuid_match:
            spec_opp = db.query(RevenueOpportunity).filter(RevenueOpportunity.id == uuid.UUID(uuid_match.group(0)), RevenueOpportunity.merchant_id == merchant_id).one_or_none()
            if spec_opp:
                top = {
                    "id": str(spec_opp.id), "type": spec_opp.type, "reach_count": spec_opp.reach_count,
                    "estimated_revenue_amount": float(spec_opp.estimated_revenue_amount),
                    "source_product_id": str(spec_opp.source_product_id) if spec_opp.source_product_id else None,
                    "target_product_id": str(spec_opp.target_product_id) if spec_opp.target_product_id else None,
                }

        if not top:
            opp_result = get_revenue_opportunities(db, merchant_id, limit=1)
            if not opp_result.get("found"):
                reply = "I don't have an opportunity to build a campaign from yet. Run an analysis first."
                _log_message(db, session.id, "assistant", reply)
                return {"reply": reply, "intent": "CREATE_CAMPAIGN_DRAFT", "tool_result": None}
            top = opp_result["opportunities"][0]

        resolved_discount = discount if discount is not None else 10.0
        product_ids = [uuid.UUID(p) for p in [top["source_product_id"], top["target_product_id"]] if p]
        if not product_ids:
            first_product = db.query(Product).filter(Product.merchant_id == merchant_id).first()
            if first_product:
                product_ids = [first_product.id]

        try:
            draft_payload = CreateCampaignDraftInput(
                opportunity_id=uuid.UUID(top["id"]), name=f"Auto campaign: {top['type']}", objective=top["type"],
                product_ids=product_ids, discount_percent=resolved_discount, budget_amount=min(4500.0, max(500.0, top["estimated_revenue_amount"] * 0.1)),
            )
        except ValidationError as e:
            reply = f"That request doesn't validate: {e.errors()[0]['msg']}."
            _log_message(db, session.id, "assistant", reply)
            return {"reply": reply, "intent": "CREATE_CAMPAIGN_DRAFT", "error": str(e)}

        draft_action = create_campaign_draft(db, merchant_id, session.id, draft_payload)
        if draft_action.status == "blocked":
            reply = f"I can't create that campaign: {draft_action.error}"
            _log_message(db, session.id, "assistant", reply)
            return {"reply": reply, "intent": "CREATE_CAMPAIGN_DRAFT", "action_id": str(draft_action.id)}

        campaign_id = uuid.UUID(draft_action.result_json["campaign_id"])
        approval_payload = RequestCampaignApprovalInput(campaign_id=campaign_id)
        approval_action = request_campaign_approval(db, merchant_id, session.id, approval_payload)

        if approval_action.status == "blocked":
            reply = f"Campaign drafted, but submitting it for approval was blocked: {approval_action.error}"
        elif approval_action.status == "pending_approval":
            reply = (
                f"Campaign drafted at {resolved_discount:.0f}% discount and submitted for your approval "
                f"(policy passed, permission requires sign-off). Check the Approval Center."
            )
        else:
            reply = "Campaign drafted and executed automatically (permission allows it without approval)."

        _log_message(db, session.id, "assistant", reply)
        return {
            "reply": reply, "intent": "CREATE_CAMPAIGN_DRAFT",
            "draft_action_id": str(draft_action.id), "approval_action_id": str(approval_action.id),
        }

    if name == "VIEW_OPPORTUNITIES":
        result = get_revenue_opportunities(db, merchant_id, limit=3)
        _log_tool_call(db, session.id, "get_revenue_opportunities", {}, result, "ok")
        if not result.get("found"):
            reply = "I didn't find any open revenue opportunities right now. Try running an analysis first."
        else:
            top = result["opportunities"][0]
            reply = (
                f"Your top opportunity is a {top['type'].replace('_', '-')} play reaching "
                f"{top['reach_count']} customers, estimated at ₹{top['estimated_revenue_amount']:,.0f} "
                f"(ESTIMATED), priority score {top['priority_score']:.0f}, risk: {top['risk_level']}."
            )
        _log_message(db, session.id, "assistant", reply)
        return {"reply": reply, "intent": "VIEW_OPPORTUNITIES", "tool_result": result}

    if name == "VIEW_REVENUE":
        from app.agents.read_tools import get_revenue_metrics

        result = get_revenue_metrics(db, merchant_id)
        _log_tool_call(db, session.id, "get_revenue_metrics", {}, result, "ok")
        reply = (
            f"Total revenue is ₹{result['total_revenue']:,.0f} across {result['order_count']} paid orders "
            f"(AOV ₹{result['average_order_value']:,.0f}, repeat purchase rate {result['repeat_purchase_rate']:.0%})."
        )
        _log_message(db, session.id, "assistant", reply)
        return {"reply": reply, "intent": "VIEW_REVENUE", "tool_result": result}

    if name == "VIEW_SEGMENTS":
        from app.agents.read_tools import get_customer_segments

        result = get_customer_segments(db, merchant_id)
        _log_tool_call(db, session.id, "get_customer_segments", {}, result, "ok")
        segments = result["segments"]
        summary = ", ".join(f"{v['label']}: {v['customer_count']}" for v in segments.values())
        reply = f"Customer segments — {summary}." if segments else "No segments computed yet. Run analytics first."
        _log_message(db, session.id, "assistant", reply)
        return {"reply": reply, "intent": "VIEW_SEGMENTS", "tool_result": result}

    if name == "SIMULATE_CAMPAIGN":
        if discount is None:
            reply = "Tell me a discount percentage to simulate, e.g. \"simulate a 10% discount\"."
            _log_message(db, session.id, "assistant", reply)
            return {"reply": reply, "intent": "SIMULATE_CAMPAIGN", "tool_result": None}

        opp_result = get_revenue_opportunities(db, merchant_id, limit=1)
        if not opp_result.get("found"):
            reply = "I don't have an opportunity to simulate against yet. Run an analysis first."
            _log_message(db, session.id, "assistant", reply)
            return {"reply": reply, "intent": "SIMULATE_CAMPAIGN", "tool_result": None}

        top = opp_result["opportunities"][0]
        product_ids = [uuid.UUID(p) for p in [top["source_product_id"], top["target_product_id"]] if p]
        try:
            payload = SimulateCampaignInput(product_ids=product_ids, discount_percent=discount)
        except ValidationError as e:
            reply = f"That request doesn't validate: {e.errors()[0]['msg']}."
            _log_message(db, session.id, "assistant", reply)
            return {"reply": reply, "intent": "SIMULATE_CAMPAIGN", "error": str(e)}

        action = simulate_campaign_action(db, merchant_id, session.id, payload)
        sim = action.result_json
        roi_text = f"{sim['roi']:.1f}x" if sim.get("roi") is not None else "undefined (zero campaign cost)"
        reply = (
            f"At {discount:.0f}% discount: ~{sim['expected_orders']:.0f} expected orders, "
            f"₹{sim['expected_revenue']:,.0f} expected revenue (ESTIMATED), discount cost ₹{sim['discount_cost']:,.0f}, "
            f"ROI {roi_text}."
        )
        _log_message(db, session.id, "assistant", reply)
        return {"reply": reply, "intent": "SIMULATE_CAMPAIGN", "tool_result": sim, "action_id": str(action.id)}

    if name == "PRODUCT_LOOKUP":
        # Grounded lookup — deliberately returns "not found" rather than
        # guessing when the referenced product doesn't exist in the catalog.
        result = get_product_details(db, merchant_id, product_name_query=user_text)
        _log_tool_call(db, session.id, "get_product_details", {"query": user_text}, result, "ok")
        if not result.get("found"):
            reply = "I couldn't find that product in the merchant catalog."
        else:
            reply = f"{result['name']} ({result['sku']}) is ₹{result['price_amount']:,.0f}, stock: {result['stock_status']}."
        _log_message(db, session.id, "assistant", reply)
        return {"reply": reply, "intent": "PRODUCT_LOOKUP", "tool_result": result}

    reply = (
        "I can help with revenue opportunities, customer segments, campaign simulations, and creating campaigns. "
        "Try asking: 'What's my top opportunity?' or 'Simulate a 10% discount'."
    )
    _log_message(db, session.id, "assistant", reply)
    return {"reply": reply, "intent": "UNKNOWN", "tool_result": None}
