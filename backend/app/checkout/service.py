from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from sqlalchemy.orm import Session

from app.attribution.service import settle_paid_payment
from app.buyer.service import _active_cart, serialize_cart
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.razorpay.exceptions import PaymentProviderError
from app.integrations.razorpay.factory import get_payment_provider
from app.models.catalog import Product
from app.models.commerce import CartItem, Order, OrderItem, Payment
from app.models.customers import Customer
from app.models.ops import AuditLog


def _cart_or_error(db: Session, merchant_id: uuid.UUID, session_ref: str):
    cart = _active_cart(db, merchant_id, session_ref)
    if not cart:
        raise AppError("CART_NOT_FOUND", "No active cart exists for this buyer session.", status_code=404)
    state = serialize_cart(db, cart)
    if not state["items"]:
        raise AppError("EMPTY_CART", "Add at least one product before checkout.", status_code=409)
    if not state["can_checkout"]:
        raise AppError("CART_UNAVAILABLE", "Refresh the cart before checkout; one or more products are unavailable.", status_code=409, details={"issues": state["issues"]})
    return cart, state


def preview_checkout(db: Session, merchant_id: uuid.UUID, session_ref: str) -> dict:
    cart, state = _cart_or_error(db, merchant_id, session_ref)
    settings = get_settings()
    return {
        "preview_id": str(cart.id),
        "cart_id": str(cart.id),
        "items": state["items"],
        "subtotal": state["subtotal"],
        "discount": {"amount": 0.0, "currency": "INR"},
        "shipping": state["shipping"],
        "total": state["total"],
        "currency": "INR",
        "payment_provider": settings.payment_mode_label,
        "requires_explicit_confirmation": True,
        "expires_in_seconds": 600,
    }


def _checkout_result(order: Order, payment: Payment) -> dict:
    return {
        "status": "payment_pending" if order.status == "pending" else "confirmed",
        "order_id": str(order.id),
        "payment_id": str(payment.id),
        "provider": payment.provider,
        "provider_order_id": payment.provider_order_id,
        "amount": {"amount": float(order.total_amount), "currency": order.currency},
        "order_status": order.status,
        "payment_status": payment.status,
        "demo_payment_available": payment.provider == "mock" and get_settings().DEMO_MODE,
    }


def confirm_checkout(
    db: Session,
    merchant_id: uuid.UUID,
    *,
    session_ref: str,
    preview_id: uuid.UUID,
    confirmed: bool,
    buyer_name: str,
    buyer_email: str,
    idempotency_key: str | None,
) -> dict:
    if not confirmed:
        raise AppError("CONFIRMATION_REQUIRED", "Explicit confirmation is required before creating a payment order.", status_code=422)
    cart, state = _cart_or_error(db, merchant_id, session_ref)
    if str(cart.id) != str(preview_id):
        raise AppError("STALE_CHECKOUT_PREVIEW", "The checkout preview does not match the current cart. Preview it again.", status_code=409)

    key = idempotency_key or f"ai_buyer_checkout_{cart.id}"
    existing_payment = db.query(Payment).filter(Payment.idempotency_key == key).one_or_none()
    if existing_payment and existing_payment.order_id:
        order = db.get(Order, existing_payment.order_id)
        return _checkout_result(order, existing_payment)

    customer = db.query(Customer).filter(Customer.merchant_id == merchant_id, Customer.email.ilike(buyer_email.strip())).one_or_none()
    if not customer:
        customer = Customer(
            merchant_id=merchant_id,
            name=buyer_name.strip(),
            email=buyer_email.strip().lower(),
            external_ref=f"ai_buyer:{cart.session_ref}",
            total_spend=0,
            order_count=0,
        )
        db.add(customer)
        db.flush()

    live_items = db.query(CartItem, Product).join(Product, Product.id == CartItem.product_id).filter(CartItem.cart_id == cart.id).all()
    subtotal = round(sum(float(product.price_amount) * item.quantity for item, product in live_items), 2)
    order = Order(
        merchant_id=merchant_id,
        customer_id=customer.id,
        cart_id=cart.id,
        status="pending",
        subtotal_amount=subtotal,
        discount_amount=0,
        shipping_amount=0,
        total_amount=subtotal,
        currency="INR",
        source="ai_buyer",
    )
    db.add(order)
    db.flush()
    for item, product in live_items:
        db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=item.quantity, unit_price_amount=product.price_amount))
    db.flush()

    provider = get_payment_provider(merchant_id=merchant_id)
    try:
        provider_result = provider.create_order(amount=int(subtotal), currency="INR", receipt=str(order.id))
    except PaymentProviderError as exc:
        db.rollback()
        raise AppError("PAYMENT_PROVIDER_ERROR", "The payment provider could not create an order. Your cart was not changed.", status_code=502, details={"provider_error": str(exc)}) from exc

    payment = Payment(
        merchant_id=merchant_id,
        order_id=order.id,
        provider=provider_result["provider"],
        provider_order_id=provider_result["provider_order_id"],
        amount=subtotal,
        currency="INR",
        status="created",
        idempotency_key=key,
    )
    db.add(payment)
    db.add(AuditLog(
        merchant_id=merchant_id,
        action="CHECKOUT_ORDER_CREATED",
        tool="ai_buyer_checkout",
        input_summary=f"order={order.id} amount={subtotal}",
        reason="Buyer explicitly confirmed the server-recomputed cart total.",
        result="success",
        external_id=str(order.id),
        created_at=datetime.now(UTC),
    ))
    db.commit()
    return _checkout_result(order, payment)


def verify_checkout_payment(
    db: Session,
    merchant_id: uuid.UUID,
    *,
    order_id: uuid.UUID,
    provider_payment_id: str | None,
    razorpay_signature: str | None,
    demo: bool,
) -> dict:
    payment = (
        db.query(Payment)
        .filter(Payment.merchant_id == merchant_id, Payment.order_id == order_id)
        .one_or_none()
    )
    if not payment:
        raise AppError("PAYMENT_NOT_FOUND", "No payment exists for this order.", status_code=404)
    settings = get_settings()

    if payment.provider == "mock":
        if not (demo and settings.DEMO_MODE):
            raise AppError("DEMO_PAYMENT_REQUIRED", "This order uses Demo Payment Mode. Complete it only through the demo payment control.", status_code=403)
        payment_id = provider_payment_id or f"mock_pay_{uuid.uuid4().hex[:16]}"
    else:
        if not provider_payment_id or not razorpay_signature or not settings.RAZORPAY_KEY_SECRET:
            raise AppError("PAYMENT_SIGNATURE_REQUIRED", "Razorpay payment ID, signature, and server credentials are required.", status_code=422)
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{payment.provider_order_id}|{provider_payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, razorpay_signature):
            raise AppError("INVALID_PAYMENT_SIGNATURE", "Payment verification failed.", status_code=400)
        payment_id = provider_payment_id

    result = settle_paid_payment(db, payment, provider_payment_id=payment_id, event_type="payment.verified")
    db.commit()
    return {**result, "order_status": "paid", "payment_status": "paid"}