"""Razorpay webhook handling. This is the server-side source of truth for
payment state — never the browser callback, per Razorpay's own guidance
that webhooks are the reliable, asynchronous notification channel while
browser redirects can be interrupted, closed, or spoofed.

Every request is verified against the RAW body bytes before anything else
happens. An unverified or duplicate event touches no state at all.
"""

import json
import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.attribution.service import settle_paid_payment
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.integrations.razorpay.client import RazorpayProvider, paise_to_rupees
from app.integrations.razorpay.mock_provider import MockPaymentProvider
from app.models.campaigns import Campaign
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem, Payment, PaymentEvent
from app.models.customers import Customer
from app.models.ops import AuditLog, RevenueAttribution, WebhookEvent

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Events that indicate a payment was actually captured against a payment
# link — these are the only ones that advance Payment/Campaign state.
PAID_EVENTS = {"payment_link.paid", "order.paid"}
TERMINAL_NON_PAID_EVENTS = {"payment_link.cancelled", "payment_link.expired", "payment.failed"}


def _verify_signature(raw_body: bytes, signature: str | None, secret: str | None) -> bool:
    if not signature or not secret:
        return False
    verifier = RazorpayProvider(key_id="unused", key_secret="unused")
    return verifier.verify_webhook_signature(payload=raw_body, signature=signature, secret=secret)


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request, db: Session = Depends(get_db), x_razorpay_signature: str | None = Header(default=None),
):
    settings = get_settings()
    raw_body = await request.body()
    received_at = datetime.now(UTC)
    event_id = request.headers.get("x-razorpay-event-id")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        body = {}
    event_type = body.get("event", "unknown")

    # The existing-event lookup happens ONCE, before any signature-
    # dependent branching, and its outcome governs everything below.
    # This closes two real bugs found while testing this endpoint:
    #
    # 1. A previously recorded event_id with processed=False (e.g. a
    #    prior invalid-signature attempt, perhaps from a webhook secret
    #    that was misconfigured at the time) must NOT permanently block
    #    a later, correctly-signed retry of the SAME event_id — Razorpay
    #    retries webhook delivery with the same event_id until it gets a
    #    2xx, so a fixed-config retry needs to be able to succeed.
    # 2. Two deliveries with the same event_id that both fail signature
    #    verification must not both try to INSERT a new row — event_id
    #    has a unique constraint, so the second insert would raise an
    #    unhandled IntegrityError instead of a clean response. The
    #    existing row is UPDATED in place instead.
    existing = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).one_or_none() if event_id else None
    if existing and existing.processed:
        return {"status": "duplicate_ignored", "event_id": event_id}

    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    signature_valid = False
    if webhook_secret:
        if settings.PAYMENT_PROVIDER == "razorpay":
            signature_valid = _verify_signature(raw_body, x_razorpay_signature, webhook_secret)
        else:
            # DEMO_MODE convenience: when running against
            # MockPaymentProvider, verification uses the same HMAC helper
            # the real provider exposes, so the demo failure-lab flow can
            # still exercise "invalid signature" without a real Razorpay
            # account.
            mock = MockPaymentProvider()
            signature_valid = bool(x_razorpay_signature) and mock.verify_webhook_signature(
                payload=raw_body, signature=x_razorpay_signature, secret=webhook_secret,
            )

    if not signature_valid:
        if existing:
            existing.received_at = received_at
            existing.failure_reason = "Signature verification failed or webhook secret not configured."
        else:
            db.add(WebhookEvent(
                provider="razorpay", event_id=event_id or f"unverified_{uuid.uuid4().hex}", event_type=event_type,
                received_at=received_at, signature_valid=False, processed=False,
                failure_reason="Signature verification failed or webhook secret not configured.",
            ))
        db.commit()
        raise AppError("INVALID_WEBHOOK_SIGNATURE", "Webhook signature verification failed.", status_code=400)

    if not event_id:
        # Razorpay always sends this header; its absence on an otherwise
        # validly-signed request is itself suspicious enough to reject
        # rather than fabricate a dedup key.
        db.add(WebhookEvent(
            provider="razorpay", event_id=f"missing_event_id_{uuid.uuid4().hex}", event_type=event_type,
            received_at=received_at, signature_valid=True, processed=False,
            failure_reason="Missing x-razorpay-event-id header — cannot guarantee idempotency.",
        ))
        db.commit()
        raise AppError("MISSING_EVENT_ID", "Webhook is missing the x-razorpay-event-id header.", status_code=400)

    if existing:
        webhook_event = existing
        webhook_event.signature_valid = True
        webhook_event.failure_reason = None
        webhook_event.received_at = received_at
    else:
        webhook_event = WebhookEvent(
            provider="razorpay", event_id=event_id, event_type=event_type, received_at=received_at,
            signature_valid=True, processed=False,
        )
        db.add(webhook_event)
    db.flush()

    try:
        result = _process_event(db, event_type, body)
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(UTC)
        db.commit()
        return {"status": "processed", "event_id": event_id, **result}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        webhook_event.processed = False
        webhook_event.failure_reason = str(exc)[:500]
        db.add(webhook_event)
        db.commit()
        # Return 200 anyway once the event is durably recorded as failed —
        # returning 5xx here would make Razorpay retry indefinitely for an
        # error that re-processing the identical payload won't fix (e.g.
        # a data mismatch), and we've already preserved the failure for
        # manual investigation via the audit/webhook_events tables.
        return {"status": "recorded_with_error", "event_id": event_id, "error": str(exc)[:200]}


def _process_event(db: Session, event_type: str, body: dict) -> dict:
    if event_type in PAID_EVENTS:
        if event_type == "order.paid":
            return _handle_order_paid(db, body)
        return _handle_payment_link_paid(db, body)
    if event_type in TERMINAL_NON_PAID_EVENTS:
        return _handle_terminal_non_paid(db, event_type, body)
    return {"note": f"event type '{event_type}' recorded but not acted on"}


def _handle_payment_link_paid(db: Session, body: dict) -> dict:
    payload = body.get("payload", {})
    payment_link_entity = payload.get("payment_link", {}).get("entity", {})
    payment_entity = payload.get("payment", {}).get("entity", {})

    plink_id = payment_link_entity.get("id")
    amount_paise = payment_entity.get("amount") or payment_link_entity.get("amount_paid")
    razorpay_payment_id = payment_entity.get("id")

    payment = db.query(Payment).filter(Payment.provider_payment_link_id == plink_id).one_or_none()
    if not payment:
        raise ValueError(f"No local Payment found for provider_payment_link_id={plink_id}")

    amount_rupees = paise_to_rupees(amount_paise) if amount_paise is not None else float(payment.amount)

    payment.status = "paid"
    payment.provider_payment_id = razorpay_payment_id
    db.add(PaymentEvent(payment_id=payment.id, event_type="payment_link.paid", raw_status="captured", occurred_at=datetime.now(UTC)))

    campaign = db.get(Campaign, payment.campaign_id) if payment.campaign_id else None
    if campaign:
        campaign.actual_revenue_amount = float(campaign.actual_revenue_amount) + amount_rupees
        if campaign.status == "running":
            campaign.status = "completed"

    # Attempt to attribute this revenue to a known customer by matching
    # the payer's email against this merchant's customer records. If a
    # match is found, a real Order (+ OrderItems, from the campaign's
    # actual product list) is created — genuine data representing a
    # genuine purchase, not a placeholder — because RevenueAttribution
    # requires an order_id, and a campaign-wide payment link has no
    # existing Order until we know who paid. If no match is found, the
    # Payment/Campaign state above is still updated (that's factual
    # regardless of who paid), but nothing is fabricated: no Order, no
    # RevenueAttribution — attribution requires knowing WHO paid, and a
    # generic campaign-wide link genuinely may not tell us that.
    customer_email = (payment_link_entity.get("customer") or {}).get("email")
    customer = None
    if customer_email:
        customer = db.query(Customer).filter(Customer.merchant_id == payment.merchant_id, Customer.email.ilike(customer_email)).one_or_none()

    attribution_created = False
    if customer and campaign:
        product_ids = [uuid.UUID(p) for p in (campaign.product_ids_json or [])]
        products = db.query(Product).filter(Product.id.in_(product_ids)).all() if product_ids else []
        subtotal = sum(float(p.price_amount) for p in products) or amount_rupees
        discount_amount = round(subtotal * float(campaign.discount_percent) / 100, 2)

        order = Order(
            merchant_id=payment.merchant_id, customer_id=customer.id, status="paid",
            subtotal_amount=subtotal, discount_amount=discount_amount, shipping_amount=0,
            total_amount=amount_rupees, currency="INR", source="merchant_campaign",
        )
        db.add(order)
        db.flush()
        for product in products:
            db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1, unit_price_amount=product.price_amount))

        payment.order_id = order.id
        db.add(RevenueAttribution(
            merchant_id=payment.merchant_id, campaign_id=payment.campaign_id, customer_id=customer.id,
            order_id=order.id, payment_id=payment.id, attribution_type="attributed",
            amount=amount_rupees, created_at=datetime.now(UTC),
        ))
        attribution_created = True

    db.add(AuditLog(
        merchant_id=payment.merchant_id, action="PAYMENT_LINK_PAID", tool="razorpay_webhook",
        input_summary=f"payment_link={plink_id} amount={amount_rupees}",
        reason="payment_link.paid webhook received and verified", policy_result="n/a", permission_result="n/a",
        external_id=str(payment.id), result="success",
        recovery_action=None if attribution_created else "No matching customer email found; payment recorded without per-customer attribution.",
        created_at=datetime.now(UTC),
    ))
    db.flush()

    return {"payment_id": str(payment.id), "amount": amount_rupees, "attribution_created": attribution_created}


def _handle_order_paid(db: Session, body: dict) -> dict:
    payload = body.get("payload", {})
    order_entity = payload.get("order", {}).get("entity", {})
    payment_entity = payload.get("payment", {}).get("entity", {})
    provider_order_id = order_entity.get("id")
    provider_payment_id = payment_entity.get("id")
    payment = db.query(Payment).filter(Payment.provider_order_id == provider_order_id).one_or_none()
    if not payment:
        raise ValueError(f"No local Payment found for provider_order_id={provider_order_id}")
    return settle_paid_payment(
        db,
        payment,
        provider_payment_id=provider_payment_id,
        event_type="order.paid",
    )


def _handle_terminal_non_paid(db: Session, event_type: str, body: dict) -> dict:
    payload = body.get("payload", {})
    payment_link_entity = payload.get("payment_link", {}).get("entity", {})
    plink_id = payment_link_entity.get("id")

    payment = db.query(Payment).filter(Payment.provider_payment_link_id == plink_id).one_or_none()
    if not payment:
        return {"note": f"no local payment for {plink_id}, nothing to update"}

    new_status = "failed" if event_type == "payment.failed" else "created"
    db.add(PaymentEvent(payment_id=payment.id, event_type=event_type, raw_status=payment_link_entity.get("status", event_type), occurred_at=datetime.now(UTC)))
    if event_type == "payment.failed":
        payment.status = new_status
    db.flush()
    return {"payment_id": str(payment.id), "event": event_type}
