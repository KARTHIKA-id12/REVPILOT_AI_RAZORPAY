"""Failure injection for the Failure Lab. This does NOT fake a failure
response — it makes the REAL payment provider raise the REAL exception
class the Action Pipeline already knows how to handle (see
app/agents/pipeline.py's try/except around provider.create_payment_link).
Every downstream effect — the campaign being marked 'failed', the audit
log entry, the safe-retry-via-idempotency-key behavior — is the actual
production code path, not a scripted demo response.

Deliberately in-memory and single-process: this is a demo/QA feature
(explicitly out of scope for a multi-worker production deployment, where
a per-process dict wouldn't be visible to other workers), gated by
DEMO_MODE, and the injection is single-shot — it fires exactly once per
call to `arm()`, then clears itself, so a demo can't accidentally leave
the payment provider permanently broken.
"""

import threading
import uuid

from app.integrations.razorpay.exceptions import PaymentProviderError, RazorpayAPIError, RazorpayTimeoutError

_lock = threading.Lock()
_armed: dict[uuid.UUID, str] = {}

SCENARIO_EXCEPTIONS: dict[str, type[PaymentProviderError]] = {
    "payment_timeout": RazorpayTimeoutError,
    "payment_provider_error": RazorpayAPIError,
}


def arm(merchant_id: uuid.UUID, scenario: str) -> None:
    if scenario not in SCENARIO_EXCEPTIONS:
        raise ValueError(f"Unknown failure scenario: {scenario}")
    with _lock:
        _armed[merchant_id] = scenario


def disarm(merchant_id: uuid.UUID) -> None:
    with _lock:
        _armed.pop(merchant_id, None)


def is_armed(merchant_id: uuid.UUID) -> bool:
    with _lock:
        return merchant_id in _armed


def maybe_raise(merchant_id: uuid.UUID) -> None:
    """Called from inside the real provider wrapper before a real payment
    call would go out. If armed, consumes the single shot and raises the
    real exception class; otherwise does nothing and the real call
    proceeds normally."""
    with _lock:
        scenario = _armed.pop(merchant_id, None)
    if scenario is None:
        return
    exc_class = SCENARIO_EXCEPTIONS[scenario]
    if exc_class is RazorpayTimeoutError:
        raise RazorpayTimeoutError("Razorpay request timed out after 15.0s (injected by Failure Lab)")
    raise RazorpayAPIError("Razorpay returned HTTP 502 (injected by Failure Lab)", status_code=502, razorpay_error_code="GATEWAY_ERROR")


class FailureInjectingProvider:
    """Wraps a real PaymentProvider. Delegates every call unchanged
    UNLESS a single-shot failure is armed for this merchant, in which
    case it raises before ever calling the wrapped provider — so no real
    (or mock) payment link is created on the failing attempt, exactly
    matching what a genuine provider-side failure would look like from
    the caller's perspective."""

    def __init__(self, wrapped, merchant_id: uuid.UUID):
        self._wrapped = wrapped
        self._merchant_id = merchant_id

    def create_payment_link(self, **kwargs):
        maybe_raise(self._merchant_id)
        return self._wrapped.create_payment_link(**kwargs)

    def create_order(self, **kwargs):
        maybe_raise(self._merchant_id)
        return self._wrapped.create_order(**kwargs)

    def verify_webhook_signature(self, **kwargs):
        return self._wrapped.verify_webhook_signature(**kwargs)
