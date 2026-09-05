"""Razorpay integration exceptions. The Action Pipeline catches
PaymentProviderError specifically so a Razorpay outage or auth failure
becomes a clean, audited 'failed' action — never an unhandled 500, and
never a partial Payment row left in an ambiguous state."""


class PaymentProviderError(Exception):
    """Base class for anything that goes wrong talking to a payment provider."""


class RazorpayAuthenticationError(PaymentProviderError):
    """Invalid or mismatched API credentials (wrong key_id/key_secret,
    or test-mode key used where live is expected, etc.)."""


class RazorpayAPIError(PaymentProviderError):
    """Razorpay returned a non-2xx response for reasons other than auth
    (validation error, rate limit, 5xx, etc.)."""

    def __init__(self, message: str, status_code: int | None = None, razorpay_error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.razorpay_error_code = razorpay_error_code


class RazorpayTimeoutError(PaymentProviderError):
    """The request to Razorpay timed out — the caller cannot know
    whether the operation actually completed on Razorpay's side."""


class RazorpaySignatureError(PaymentProviderError):
    """A webhook signature failed verification — the payload must be
    treated as untrusted and never processed."""
