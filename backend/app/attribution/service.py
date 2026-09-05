from __future__ import annotations

import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.campaigns import Campaign
from app.models.catalog import InventoryEvent, Product
from app.models.commerce import Cart, Order, OrderItem, Payment, PaymentEvent
from app.models.customers import Customer
from app.models.ops import AuditLog, RevenueAttribution


def summarize_attribution(db: Session, merchant_id: uuid.UUID) -> dict:
    paid_orders = db.query(Order).filter(Order.merchant_id == merchant_id, Order.status == "paid")
    total_revenue = float(paid_orders.with_entities(func.coalesce(func.sum(Order.total_amount), 0)).scalar() or 0)
    order_count = paid_orders.count()
    attributed = db.query(RevenueAttribution).filter(RevenueAttribution.merchant_id == merchant_id)
    ai_revenue = float(
        attributed.filter(RevenueAttribution.attribution_type == "ai_buyer")
        .with_entities(func.coalesce(func.sum(RevenueAttribution.amount), 0))
        .scalar()
        or 0
    )
    campaign_revenue = float(
        attributed.filter(RevenueAttribution.campaign_id.is_not(None))
        .with_entities(func.coalesce(func.sum(RevenueAttribution.amount), 0))
        .scalar()
        or 0
    )
    customer_count = attributed.with_entities(func.count(func.distinct(RevenueAttribution.customer_id))).scalar() or 0
    return {
        "total_revenue": round(total_revenue, 2),
        "ai_attributed_revenue": round(ai_revenue, 2),
        "campaign_revenue": round(campaign_revenue, 2),
        "order_count": order_count,
        "customers_converted": int(customer_count),
        "average_order_value": round(total_revenue / order_count, 2) if order_count else 0,
        "measurement_note": "Revenue is attributed to verified paid orders. Incrementality is not claimed without a controlled experiment.",
    }


def settle_paid_payment(
    db: Session,
    payment: Payment,
    *,
    provider_payment_id: str | None = None,
    event_type: str = "payment.verified",
) -> dict:
    """Settle a verified payment exactly once.

    This is the one state transition shared by Razorpay webhooks, the
    server-side checkout verification endpoint, and demo payment completion.
    Replaying any of those signals returns the existing result without
    decrementing stock or counting revenue twice.
    """
    if payment.status == "paid":
        attribution = db.query(RevenueAttribution).filter(RevenueAttribution.payment_id == payment.id).one_or_none()
        return {
            "payment_id": str(payment.id),
            "order_id": str(payment.order_id) if payment.order_id else None,
            "attribution_created": attribution is not None,
            "duplicate": True,
        }

    order = db.get(Order, payment.order_id) if payment.order_id else None
    if not order:
        raise AppError("ORDER_NOT_FOUND", "The payment is not linked to a local order.", status_code=409)

    for item in db.query(OrderItem).filter(OrderItem.order_id == order.id).all():
        product = db.get(Product, item.product_id)
        if not product or product.status != "active" or product.stock_qty < item.quantity:
            raise AppError("OUT_OF_STOCK", "A product became unavailable before payment settlement.", status_code=409)

    now = datetime.now(UTC)
    payment.status = "paid"
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    order.status = "paid"
    customer = db.get(Customer, order.customer_id)
    if customer:
        customer.total_spend = float(customer.total_spend or 0) + float(order.total_amount)
        customer.order_count = int(customer.order_count or 0) + 1
        customer.first_order_at = customer.first_order_at or now
        customer.last_order_at = now

    for item in db.query(OrderItem).filter(OrderItem.order_id == order.id).all():
        product = db.get(Product, item.product_id)
        product.stock_qty -= item.quantity
        product.stock_status = "out_of_stock" if product.stock_qty == 0 else ("low_stock" if product.stock_qty < 10 else "in_stock")
        db.add(InventoryEvent(product_id=product.id, delta=-item.quantity, reason="order_paid", occurred_at=now))

    if order.cart_id:
        cart = db.get(Cart, order.cart_id)
        if cart:
            cart.status = "converted"

    event_exists = (
        db.query(PaymentEvent)
        .filter(PaymentEvent.payment_id == payment.id, PaymentEvent.event_type == event_type)
        .first()
    )
    if not event_exists:
        db.add(PaymentEvent(payment_id=payment.id, event_type=event_type, raw_status="captured", occurred_at=now))

    attribution = db.query(RevenueAttribution).filter(RevenueAttribution.payment_id == payment.id).one_or_none()
    if not attribution:
        attribution_type = "campaign" if payment.campaign_id else ("ai_buyer" if order.source == "ai_buyer" else "direct")
        attribution = RevenueAttribution(
            merchant_id=payment.merchant_id,
            campaign_id=payment.campaign_id,
            customer_id=order.customer_id,
            order_id=order.id,
            payment_id=payment.id,
            attribution_type=attribution_type,
            amount=order.total_amount,
            attribution_timestamp=now,
            created_at=now,
        )
        db.add(attribution)

    campaign = db.get(Campaign, payment.campaign_id) if payment.campaign_id else None
    if campaign:
        campaign.actual_revenue_amount = float(campaign.actual_revenue_amount) + float(order.total_amount)
        if campaign.status == "running":
            campaign.status = "completed"

    db.add(AuditLog(
        merchant_id=payment.merchant_id,
        action="PAYMENT_SETTLED",
        tool="payment_verification",
        input_summary=f"order={order.id} payment={payment.id} amount={order.total_amount}",
        reason="Payment was verified and revenue was attributed.",
        policy_result="n/a",
        permission_result="n/a",
        external_id=str(payment.id),
        result="success",
        created_at=now,
    ))
    db.flush()
    return {
        "payment_id": str(payment.id),
        "order_id": str(order.id),
        "attribution_created": True,
        "attribution_type": attribution.attribution_type,
        "amount": float(order.total_amount),
        "duplicate": False,
    }