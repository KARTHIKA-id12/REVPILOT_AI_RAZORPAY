"""Real Razorpay integration. Every endpoint, field name, and behavior
here was verified against official Razorpay documentation before writing
this file (see docs/product-decisions.md for the source URLs and the date
verified) — nothing is invented or assumed from training data or SDK
familiarity.

Verified facts this implementation depends on:
- Orders:        POST https://api.razorpay.com/v1/orders
- Payment Links: POST https://api.razorpay.com/v1/payment_links
- Auth:          HTTP Basic, key_id as username, key_secret as password
- Amounts:       integer, in the smallest currency subunit (paise for INR) —
                 NOT the same unit our internal Payment.amount uses (whole
                 rupees), so every amount is converted here, once, in one
                 place, rather than trusting callers to remember.
- Webhook signature: X-Razorpay-Signature header = HMAC-SHA256 hex digest
                 of the RAW request body, keyed with a webhook secret set
                 in the Razorpay dashboard (distinct from the API secret).
                 Must be verified against the exact raw bytes received —
                 re-serializing parsed JSON before verifying can silently
                 reorder keys and break a legitimate signature.
- Webhook idempotency: the `x-razorpay-event-id` header is unique per
  event and is what webhook_events.event_id stores for deduplication.
"""

import hashlib
import hmac

import httpx

from app.integrations.razorpay.exceptions import (
    RazorpayAPIError,
    RazorpayAuthenticationError,
    RazorpayTimeoutError,
)

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


def rupees_to_paise(amount_in_rupees: float) -> int:
    """Razorpay requires amounts in the smallest currency subunit. Our
    internal ledger (Payment.amount, Campaign.budget_amount, etc.) is
    stored in whole rupees as a Decimal/float. Missing this conversion
    would silently create a real payment link for 1/100th the intended
    amount — this function exists so that conversion happens in exactly
    one place, tested explicitly, rather than being re-derived (and
    potentially forgotten) at every call site."""
    return round(amount_in_rupees * 100)


def paise_to_rupees(amount_in_paise: int) -> float:
    return round(amount_in_paise / 100, 2)


class RazorpayProvider:
    """Implements the PaymentProvider protocol (see
    app/integrations/razorpay/interfaces.py) against the real Razorpay
    API. Selected by app/integrations/razorpay/factory.py only when
    PAYMENT_PROVIDER=razorpay and both RAZORPAY_KEY_ID and
    RAZORPAY_KEY_SECRET are configured — otherwise MockPaymentProvider is
    used and the UI labels results 'Demo Payment Mode', never presented
    as a real transaction."""

    def __init__(self, key_id: str, key_secret: str, timeout_seconds: float = 15.0):
        self._auth = (key_id, key_secret)
        self._timeout = timeout_seconds

    def _post(self, path: str, json_body: dict) -> dict:
        try:
            response = httpx.post(f"{RAZORPAY_BASE_URL}{path}", json=json_body, auth=self._auth, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise RazorpayTimeoutError(f"Razorpay request to {path} timed out after {self._timeout}s") from exc
        except httpx.RequestError as exc:
            raise RazorpayAPIError(f"Network error calling Razorpay: {exc}") from exc

        if response.status_code == 401:
            raise RazorpayAuthenticationError("Razorpay rejected the API credentials (check RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET).")
        if response.status_code >= 400:
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            error = body.get("error", {})
            raise RazorpayAPIError(
                error.get("description", f"Razorpay returned HTTP {response.status_code}"),
                status_code=response.status_code, razorpay_error_code=error.get("code"),
            )
        return response.json()

    def create_payment_link(self, *, amount: int, currency: str, reference_id: str, description: str) -> dict:
        """`amount` here is treated as whole currency units (matching the
        PaymentProvider protocol's existing MockPaymentProvider
        behavior) and converted to paise before calling Razorpay."""
        body = self._post("/payment_links", {
            "amount": rupees_to_paise(amount),
            "currency": currency,
            "reference_id": reference_id,
            "description": description[:2048],
            "notify": {"sms": False, "email": False},  # demo mode: never actually message a real customer
        })
        return {
            "provider": "razorpay",
            "provider_payment_link_id": body["id"],
            "short_url": body["short_url"],
            "status": body["status"],
            "amount": paise_to_rupees(body["amount"]),
            "currency": body["currency"],
            "reference_id": body.get("reference_id"),
        }

    def create_order(self, *, amount: int, currency: str, receipt: str) -> dict:
        body = self._post("/orders", {
            "amount": rupees_to_paise(amount),
            "currency": currency,
            "receipt": receipt[:40],
        })
        return {
            "provider": "razorpay", "provider_order_id": body["id"],
            "amount": paise_to_rupees(body["amount"]), "currency": body["currency"],
            "receipt": body.get("receipt"), "status": body["status"],
        }

    def verify_webhook_signature(self, *, payload: bytes, signature: str, secret: str) -> bool:
        """Verifies against the RAW request body bytes, per Razorpay's
        explicit documentation warning: 'Do not parse or cast the webhook
        request body' before computing the comparison signature."""
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
