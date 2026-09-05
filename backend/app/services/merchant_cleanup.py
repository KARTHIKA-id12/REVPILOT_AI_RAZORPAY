"""Deletes every row for a merchant in correct FK dependency order (leaves
first). Moved into the app package (out of scripts/seed_demo.py) so it has
exactly one implementation shared by:

1. The demo reset script (`scripts/seed_demo.py`, `scripts/reset_demo.py`)
2. Test fixture teardown for any test that creates a throwaway merchant

This second use matters more than it might look: several integration
tests call Action Pipeline functions that `db.commit()` internally
(agent actions must be durable even mid-test), which means a fixture's
`db.rollback()` in teardown is a no-op — the data was already committed.
Before this was extracted and used consistently, that silently leaked
permanent orphaned merchants (and their campaigns, orders, payments) into
the shared development database on every test run. This function is now
the single source of truth for "delete every trace of a merchant",
whether that's a demo reset or test cleanup.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.agent import AgentAction, AgentMessage, AgentSession, AgentToolCall
from app.models.campaigns import AgentPermission, ApprovalRequest, Campaign, CampaignEvent, CampaignTarget, PolicyRule
from app.models.catalog import InventoryEvent, Product, ProductCategory, ProductRelation
from app.models.commerce import Cart, CartItem, Order, OrderItem, Payment, PaymentEvent
from app.models.customers import Customer, CustomerSegment, CustomerSegmentMembership
from app.models.identity import Merchant, MerchantSettings, UserMerchantRole
from app.models.opportunities import RevenueOpportunity
from app.models.ops import AuditLog, Notification, RevenueAttribution, SystemEvent


def reset_merchant(db: Session, merchant_id: uuid.UUID) -> None:
    session_ids = [row[0] for row in db.query(AgentSession.id).filter(AgentSession.merchant_id == merchant_id)]
    if session_ids:
        db.execute(delete(AgentToolCall).where(AgentToolCall.session_id.in_(session_ids)))
        db.execute(delete(AgentMessage).where(AgentMessage.session_id.in_(session_ids)))
        db.execute(delete(AgentAction).where(AgentAction.session_id.in_(session_ids)))

    db.execute(delete(AuditLog).where(AuditLog.merchant_id == merchant_id))
    db.execute(delete(Notification).where(Notification.merchant_id == merchant_id))
    db.execute(delete(SystemEvent).where(SystemEvent.merchant_id == merchant_id))
    db.execute(delete(ApprovalRequest).where(ApprovalRequest.merchant_id == merchant_id))
    db.execute(delete(AgentSession).where(AgentSession.merchant_id == merchant_id))

    order_ids = [row[0] for row in db.query(Order.id).filter(Order.merchant_id == merchant_id)]
    cart_ids = [row[0] for row in db.query(Cart.id).filter(Cart.merchant_id == merchant_id)]
    campaign_ids = [row[0] for row in db.query(Campaign.id).filter(Campaign.merchant_id == merchant_id)]

    db.execute(delete(RevenueAttribution).where(RevenueAttribution.merchant_id == merchant_id))
    if order_ids:
        payment_ids_for_orders = [row[0] for row in db.query(Payment.id).filter(Payment.order_id.in_(order_ids))]
        if payment_ids_for_orders:
            db.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(payment_ids_for_orders)))
        db.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
        db.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    if campaign_ids:
        payment_ids_for_campaigns = [row[0] for row in db.query(Payment.id).filter(Payment.campaign_id.in_(campaign_ids))]
        if payment_ids_for_campaigns:
            db.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(payment_ids_for_campaigns)))
        db.execute(delete(Payment).where(Payment.campaign_id.in_(campaign_ids)))
        db.execute(delete(CampaignEvent).where(CampaignEvent.campaign_id.in_(campaign_ids)))
        db.execute(delete(CampaignTarget).where(CampaignTarget.campaign_id.in_(campaign_ids)))
    if cart_ids:
        db.execute(delete(CartItem).where(CartItem.cart_id.in_(cart_ids)))

    db.execute(delete(Campaign).where(Campaign.merchant_id == merchant_id))
    db.execute(delete(Order).where(Order.merchant_id == merchant_id))
    db.execute(delete(Cart).where(Cart.merchant_id == merchant_id))

    customer_ids = [row[0] for row in db.query(Customer.id).filter(Customer.merchant_id == merchant_id)]
    if customer_ids:
        db.execute(delete(CustomerSegmentMembership).where(CustomerSegmentMembership.customer_id.in_(customer_ids)))
    db.execute(delete(Customer).where(Customer.merchant_id == merchant_id))
    db.execute(delete(CustomerSegment).where(CustomerSegment.merchant_id == merchant_id))

    db.execute(delete(RevenueOpportunity).where(RevenueOpportunity.merchant_id == merchant_id))

    product_ids = [row[0] for row in db.query(Product.id).filter(Product.merchant_id == merchant_id)]
    if product_ids:
        db.execute(delete(ProductRelation).where(ProductRelation.product_id.in_(product_ids)))
        db.execute(delete(InventoryEvent).where(InventoryEvent.product_id.in_(product_ids)))
    db.execute(delete(Product).where(Product.merchant_id == merchant_id))
    db.execute(delete(ProductCategory).where(ProductCategory.merchant_id == merchant_id))

    db.execute(delete(PolicyRule).where(PolicyRule.merchant_id == merchant_id))
    db.execute(delete(AgentPermission).where(AgentPermission.merchant_id == merchant_id))
    db.execute(delete(UserMerchantRole).where(UserMerchantRole.merchant_id == merchant_id))
    db.execute(delete(MerchantSettings).where(MerchantSettings.merchant_id == merchant_id))
    db.execute(delete(Merchant).where(Merchant.id == merchant_id))
    db.commit()
