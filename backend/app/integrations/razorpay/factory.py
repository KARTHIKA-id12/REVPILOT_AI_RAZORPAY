import uuid

from app.core.config import get_settings
from app.integrations.razorpay.mock_provider import MockPaymentProvider


def get_payment_provider(merchant_id: uuid.UUID | None = None):
    settings = get_settings()
    if settings.PAYMENT_PROVIDER == "razorpay" and settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET:
        # Implemented in Phase 12 against verified current Razorpay docs.
        from app.integrations.razorpay.client import RazorpayProvider

        provider = RazorpayProvider(key_id=settings.RAZORPAY_KEY_ID, key_secret=settings.RAZORPAY_KEY_SECRET)
    else:
        provider = MockPaymentProvider()

    if merchant_id is not None and settings.DEMO_MODE:
        from app.services.failure_injection import FailureInjectingProvider, is_armed

        if is_armed(merchant_id):
            return FailureInjectingProvider(provider, merchant_id)
    return provider
