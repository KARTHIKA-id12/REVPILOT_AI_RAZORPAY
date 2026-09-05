"""Provider interfaces. The rest of the application depends only on these
protocols, never on a concrete SDK — this is what lets us swap
MockPaymentProvider for RazorpayProvider without touching business logic.
Concrete RazorpayProvider is implemented in Phase 12, against the current
official Razorpay API docs (Orders, Payment Links, webhooks), not from
memory of an SDK version.
"""

from typing import Protocol


class PaymentLinkResult(Protocol):
    provider_payment_link_id: str
    short_url: str
    status: str


class PaymentProvider(Protocol):
    """Abstraction over 'can create/verify a chargeable link or order'."""

    def create_payment_link(self, *, amount: int, currency: str, reference_id: str, description: str) -> dict: ...

    def create_order(self, *, amount: int, currency: str, receipt: str) -> dict: ...

    def verify_webhook_signature(self, *, payload: bytes, signature: str, secret: str) -> bool: ...
