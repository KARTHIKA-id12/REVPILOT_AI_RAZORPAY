import hashlib
import hmac

from app.integrations.razorpay.client import RazorpayProvider, paise_to_rupees, rupees_to_paise
from app.integrations.razorpay.exceptions import RazorpayAPIError, RazorpayAuthenticationError, RazorpayTimeoutError


def test_rupees_to_paise_basic():
    assert rupees_to_paise(299) == 29900
    assert rupees_to_paise(1) == 100


def test_rupees_to_paise_handles_fractional_rupees_correctly():
    """This is the exact bug class this function exists to prevent: a
    missed or wrong conversion would silently charge 1/100th (or 100x)
    the intended amount on a REAL payment."""
    assert rupees_to_paise(299.35) == 29935
    assert rupees_to_paise(18999) == 1899900  # a real TechNest product price


def test_paise_to_rupees_is_the_exact_inverse():
    for rupees in [1, 100, 299.35, 18999, 4500.50]:
        paise = rupees_to_paise(rupees)
        assert paise_to_rupees(paise) == round(rupees, 2)


def test_paise_to_rupees_basic():
    assert paise_to_rupees(29900) == 299.0
    assert paise_to_rupees(100) == 1.0


def test_webhook_signature_verification_matches_documented_hmac_sha256():
    """Directly replicates Razorpay's documented algorithm: HMAC-SHA256
    hex digest of the raw body, keyed with the webhook secret."""
    provider = RazorpayProvider(key_id="unused", key_secret="unused")
    secret = "whsec_test_12345"
    raw_body = b'{"event": "payment_link.paid", "payload": {}}'

    correct_signature = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature(payload=raw_body, signature=correct_signature, secret=secret) is True


def test_webhook_signature_rejects_wrong_secret():
    provider = RazorpayProvider(key_id="unused", key_secret="unused")
    raw_body = b'{"event": "payment_link.paid"}'
    signature_with_wrong_secret = hmac.new(b"wrong_secret", raw_body, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature(payload=raw_body, signature=signature_with_wrong_secret, secret="whsec_test_12345") is False


def test_webhook_signature_rejects_tampered_body():
    """The classic attack this defends against: an attacker intercepts a
    legitimate webhook and modifies the amount before replaying it."""
    provider = RazorpayProvider(key_id="unused", key_secret="unused")
    secret = "whsec_test_12345"
    original_body = b'{"event": "payment_link.paid", "amount": 100}'
    tampered_body = b'{"event": "payment_link.paid", "amount": 999999}'

    signature_for_original = hmac.new(secret.encode(), original_body, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature(payload=tampered_body, signature=signature_for_original, secret=secret) is False


def test_api_error_carries_status_code_and_razorpay_error_code():
    exc = RazorpayAPIError("Invalid request", status_code=400, razorpay_error_code="BAD_REQUEST_ERROR")
    assert exc.status_code == 400
    assert exc.razorpay_error_code == "BAD_REQUEST_ERROR"


def test_exception_hierarchy_lets_pipeline_catch_broadly_or_narrowly():
    from app.integrations.razorpay.exceptions import PaymentProviderError

    assert issubclass(RazorpayAuthenticationError, PaymentProviderError)
    assert issubclass(RazorpayAPIError, PaymentProviderError)
    assert issubclass(RazorpayTimeoutError, PaymentProviderError)
