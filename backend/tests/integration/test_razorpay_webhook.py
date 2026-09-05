"""Integration tests for POST /api/v1/webhooks/razorpay. These exercise
the same HMAC algorithm used by the real RazorpayProvider (see
test_razorpay_client.py for the shared-logic unit verification), with a
webhook secret configured via monkeypatched settings so signature
verification is genuinely exercised end-to-end.
"""

import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.campaigns import Campaign
from app.models.commerce import Payment
from app.models.customers import Customer
from app.models.identity import Merchant
from app.models.ops import RevenueAttribution, WebhookEvent
from app.services.merchant_cleanup import reset_merchant

WEBHOOK_SECRET = "whsec_test_secret_for_ci"


@pytest.fixture(autouse=True)
def _configure_webhook_secret(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    yield


@pytest.fixture
def merchant_with_campaign_payment():
    db = SessionLocal()
    try:
        db.execute(Merchant.__table__.select().limit(1))
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")

    merchant = Merchant(name=f"Webhook Test Merchant {uuid.uuid4().hex[:6]}", category="Test", status="active")
    db.add(merchant)
    db.flush()

    customer = Customer(merchant_id=merchant.id, name="Webhook Customer", email="webhook.customer@example.com")
    db.add(customer)
    db.flush()

    campaign = Campaign(
        merchant_id=merchant.id, name="Webhook Test Campaign", objective="cross_sell",
        discount_percent=10, budget_amount=1000, status="running",
    )
    db.add(campaign)
    db.flush()

    # Unique per fixture invocation, not a fixed literal — a fixed
    # plink_id/event_id string reused across test runs collides with
    # leftover rows from prior runs (webhook_events.event_id and
    # payments.provider_payment_link_id are both globally unique, not
    # merchant-scoped, since a real Razorpay account's webhooks aren't
    # scoped to one merchant either). This was a real bug found while
    # writing these tests: a fixed literal worked once, then permanently
    # broke every subsequent run against the same persistent database.
    plink_id = f"plink_TEST_{uuid.uuid4().hex[:16]}"
    payment = Payment(
        merchant_id=merchant.id, campaign_id=campaign.id, provider="razorpay",
        provider_payment_link_id=plink_id, amount=1000.0, currency="INR",
        status="created", idempotency_key=f"test_{uuid.uuid4().hex}",
    )
    db.add(payment)
    db.commit()

    yield db, merchant.id, campaign.id, payment.id, plink_id
    reset_merchant(db, merchant.id)
    db.close()


client = TestClient(app)


def _sign(body_dict: dict) -> tuple[bytes, str]:
    raw = json.dumps(body_dict).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, signature


def _event_id() -> str:
    return f"evt_test_{uuid.uuid4().hex}"


def _payment_link_paid_payload(plink_id: str, amount_paise: int = 100000, customer_email: str | None = None) -> dict:
    return {
        "entity": "event",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id, "amount": amount_paise, "amount_paid": amount_paise, "status": "paid",
                    "customer": {"email": customer_email} if customer_email else {},
                }
            },
            "payment": {"entity": {"id": "pay_TESTPAY123", "amount": amount_paise, "status": "captured"}},
        },
    }


def test_webhook_with_invalid_signature_is_rejected_and_touches_no_state(merchant_with_campaign_payment):
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id)
    raw = json.dumps(body).encode()
    event_id = _event_id()

    response = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": "totally_wrong_signature", "x-razorpay-event-id": event_id},
    )
    assert response.status_code == 400

    payment = db.get(Payment, payment_id)
    db.refresh(payment)
    assert payment.status == "created"  # untouched

    stored = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).one_or_none()
    assert stored is not None
    assert stored.signature_valid is False
    assert stored.processed is False


def test_valid_signature_payment_link_paid_updates_payment_and_campaign(merchant_with_campaign_payment):
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id, amount_paise=100000)  # ₹1000
    raw, signature = _sign(body)
    event_id = _event_id()

    response = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": signature, "x-razorpay-event-id": event_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"

    payment = db.get(Payment, payment_id)
    db.refresh(payment)
    assert payment.status == "paid"
    assert payment.provider_payment_id == "pay_TESTPAY123"

    campaign = db.get(Campaign, campaign_id)
    db.refresh(campaign)
    assert float(campaign.actual_revenue_amount) == 1000.0
    assert campaign.status == "completed"


def test_duplicate_event_id_is_idempotent_no_double_counting(merchant_with_campaign_payment):
    """Spec: the exact duplicate-webhook scenario. Same event delivered
    twice must count revenue exactly once."""
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id, amount_paise=100000)
    raw, signature = _sign(body)
    event_id = _event_id()
    headers = {"content-type": "application/json", "x-razorpay-signature": signature, "x-razorpay-event-id": event_id}

    first = client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers)
    assert first.json()["status"] == "processed"

    second = client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers)
    assert second.json()["status"] == "duplicate_ignored"

    campaign = db.get(Campaign, campaign_id)
    db.refresh(campaign)
    assert float(campaign.actual_revenue_amount) == 1000.0  # NOT 2000 — counted exactly once

    events = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).all()
    assert len(events) == 1  # the unique constraint + application logic both hold


def test_attribution_created_when_customer_email_matches(merchant_with_campaign_payment):
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id, amount_paise=50000, customer_email="webhook.customer@example.com")
    raw, signature = _sign(body)

    response = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": signature, "x-razorpay-event-id": _event_id()},
    )
    assert response.json()["attribution_created"] is True

    attribution = db.query(RevenueAttribution).filter(RevenueAttribution.payment_id == payment_id).one()
    assert attribution.attribution_type == "attributed"
    assert float(attribution.amount) == 500.0


def test_no_attribution_fabricated_when_customer_unknown(merchant_with_campaign_payment):
    """Never invent a customer_id just to fill the row — no match means
    no attribution record, even though the payment itself is still marked paid."""
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id, amount_paise=50000, customer_email="totally-unknown@example.com")
    raw, signature = _sign(body)

    response = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": signature, "x-razorpay-event-id": _event_id()},
    )
    assert response.json()["attribution_created"] is False

    assert db.query(RevenueAttribution).filter(RevenueAttribution.payment_id == payment_id).count() == 0
    payment = db.get(Payment, payment_id)
    db.refresh(payment)
    assert payment.status == "paid"  # still updated, just not attributed to anyone


def test_missing_event_id_header_rejected(merchant_with_campaign_payment):
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id)
    raw, signature = _sign(body)

    response = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": signature},
    )
    assert response.status_code == 400


def test_unknown_payment_link_id_recorded_as_error_not_silently_dropped(merchant_with_campaign_payment):
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload("plink_DOES_NOT_EXIST_" + uuid.uuid4().hex[:8])
    raw, signature = _sign(body)
    event_id = _event_id()

    response = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": signature, "x-razorpay-event-id": event_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "recorded_with_error"

    stored = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).one()
    assert stored.processed is False
    assert stored.failure_reason is not None


def test_retry_with_same_event_id_after_invalid_signature_can_still_succeed(merchant_with_campaign_payment):
    """Regression test for a real bug found during manual testing: once
    ANY delivery for an event_id was recorded — even a rejected one due
    to a bad/misconfigured signature — a later, correctly-signed retry of
    that exact event_id was silently treated as 'duplicate' and dropped
    forever. Razorpay retries webhook delivery with the SAME event_id
    until it gets a 2xx, so a legitimate retry (e.g. after fixing a
    misconfigured webhook secret) must be able to succeed."""
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id, amount_paise=100000)
    raw, correct_signature = _sign(body)
    event_id = _event_id()

    bad_attempt = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": "wrong_signature", "x-razorpay-event-id": event_id},
    )
    assert bad_attempt.status_code == 400

    retry = client.post(
        "/api/v1/webhooks/razorpay", content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": correct_signature, "x-razorpay-event-id": event_id},
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "processed"  # NOT duplicate_ignored

    campaign = db.get(Campaign, campaign_id)
    db.refresh(campaign)
    assert float(campaign.actual_revenue_amount) == 1000.0

    # Exactly one WebhookEvent row for this event_id — updated in place,
    # not a second row that would violate the unique constraint.
    assert db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).count() == 1


def test_two_invalid_signature_deliveries_same_event_id_do_not_crash(merchant_with_campaign_payment):
    """Regression test for a latent crash bug: before the fix, a second
    invalid-signature delivery with the same event_id would attempt to
    INSERT a duplicate row and raise an unhandled IntegrityError instead
    of a clean 400."""
    db, merchant_id, campaign_id, payment_id, plink_id = merchant_with_campaign_payment
    body = _payment_link_paid_payload(plink_id)
    raw = json.dumps(body).encode()
    event_id = _event_id()
    headers = {"content-type": "application/json", "x-razorpay-signature": "wrong_signature", "x-razorpay-event-id": event_id}

    first = client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers)
    assert first.status_code == 400
    second = client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers)
    assert second.status_code == 400  # clean 400 again, not a 500

    assert db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).count() == 1
