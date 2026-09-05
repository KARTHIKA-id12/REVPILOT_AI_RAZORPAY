import hashlib
import hmac
import uuid


class MockPaymentProvider:
    """Deterministic, offline stand-in for Razorpay. The UI must always
    label results from this provider as 'Demo Payment Mode' — never
    presented as a real Razorpay Test Mode transaction (see docs/product-
    decisions.md §98)."""

    def create_payment_link(self, *, amount: int, currency: str, reference_id: str, description: str) -> dict:
        link_id = f"mock_plink_{uuid.uuid4().hex[:14]}"
        return {
            "provider": "mock",
            "provider_payment_link_id": link_id,
            "short_url": f"https://demo.revpilot.local/pay/{link_id}",
            "status": "created",
            "amount": amount,
            "currency": currency,
            "reference_id": reference_id,
            "description": description,
        }

    def create_order(self, *, amount: int, currency: str, receipt: str) -> dict:
        order_id = f"mock_order_{uuid.uuid4().hex[:14]}"
        return {"provider": "mock", "provider_order_id": order_id, "amount": amount, "currency": currency, "receipt": receipt, "status": "created"}

    def verify_webhook_signature(self, *, payload: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
