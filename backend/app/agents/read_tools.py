"""Read tools available to the AI Growth Agent. Every one of these is a
plain DB query wrapped in a stable dict shape — there is no path from
"user asks a business question" to "model answers from its own memory".
If a tool finds nothing, it returns an explicit not-found shape; the
calling agent service must surface that honestly ("I couldn't find that
product") rather than paper over it with a plausible-sounding guess.
"""

import uuid

from sqlalchemy.orm import Session

from app.analytics.metrics import compute_revenue_metrics, compute_top_products
from app.analytics.repository import (
    load_carts_df,
    load_order_items_df,
    load_orders_df,
    load_products_df,
)
from app.models.campaigns import Campaign
from app.models.catalog import Product
from app.models.customers import Customer, CustomerSegment, CustomerSegmentMembership
from app.models.opportunities import RevenueOpportunity


def get_revenue_metrics(db: Session, merchant_id: uuid.UUID) -> dict:
    orders_df = load_orders_df(db, merchant_id)
    carts_df = load_carts_df(db, merchant_id)
    return compute_revenue_metrics(orders_df, carts_df)


def get_top_products(db: Session, merchant_id: uuid.UUID, limit: int = 10) -> dict:
    order_items_df = load_order_items_df(db, merchant_id)
    products_df = load_products_df(db, merchant_id)
    return {"products": compute_top_products(order_items_df, products_df, limit=limit)}


def get_customer_segments(db: Session, merchant_id: uuid.UUID) -> dict:
    rows = (
        db.query(CustomerSegment.code, CustomerSegment.label)
        .join(CustomerSegmentMembership, CustomerSegmentMembership.segment_id == CustomerSegment.id)
        .join(Customer, Customer.id == CustomerSegmentMembership.customer_id)
        .filter(Customer.merchant_id == merchant_id)
        .distinct()
        .all()
    )
    counts = {}
    for code, label in rows:
        count = (
            db.query(CustomerSegmentMembership)
            .join(Customer, Customer.id == CustomerSegmentMembership.customer_id)
            .join(CustomerSegment, CustomerSegment.id == CustomerSegmentMembership.segment_id)
            .filter(Customer.merchant_id == merchant_id, CustomerSegment.code == code)
            .count()
        )
        counts[code] = {"label": label, "customer_count": count}
    return {"segments": counts}


def get_revenue_opportunities(db: Session, merchant_id: uuid.UUID, opportunity_type: str | None = None, limit: int = 10) -> dict:
    query = db.query(RevenueOpportunity).filter(RevenueOpportunity.merchant_id == merchant_id, RevenueOpportunity.status == "open")
    if opportunity_type:
        query = query.filter(RevenueOpportunity.type == opportunity_type)
    rows = query.order_by(RevenueOpportunity.priority_score.desc()).limit(limit).all()
    if not rows:
        return {"opportunities": [], "found": False}
    return {
        "found": True,
        "opportunities": [
            {
                "id": str(r.id), "type": r.type, "reach_count": r.reach_count,
                "estimated_revenue_amount": float(r.estimated_revenue_amount),
                "priority_score": float(r.priority_score), "risk_level": r.risk_level,
                "source_product_id": str(r.source_product_id) if r.source_product_id else None,
                "target_product_id": str(r.target_product_id) if r.target_product_id else None,
            }
            for r in rows
        ],
    }


def get_product_details(db: Session, merchant_id: uuid.UUID, product_id: uuid.UUID | None = None, product_name_query: str | None = None) -> dict:
    """Deliberately returns found=False rather than a guess when nothing
    matches — this is what prevents the AI hallucination failure mode
    (spec test: 'what is the price of a product that does not exist?')."""
    query = db.query(Product).filter(Product.merchant_id == merchant_id)
    if product_id:
        product = query.filter(Product.id == product_id).one_or_none()
    elif product_name_query:
        product = query.filter(Product.name.ilike(f"%{product_name_query}%")).first()
    else:
        return {"found": False, "reason": "no product_id or product_name_query provided"}

    if not product:
        return {"found": False, "reason": "no matching product in the merchant catalog"}

    return {
        "found": True,
        "id": str(product.id), "name": product.name, "sku": product.sku,
        "price_amount": float(product.price_amount), "currency": product.currency,
        "stock_qty": product.stock_qty, "stock_status": product.stock_status,
    }


def get_inventory(db: Session, merchant_id: uuid.UUID, product_id: uuid.UUID | None = None) -> dict:
    query = db.query(Product).filter(Product.merchant_id == merchant_id)
    if product_id:
        query = query.filter(Product.id == product_id)
    rows = query.all()
    return {"products": [{"id": str(p.id), "name": p.name, "stock_qty": p.stock_qty, "stock_status": p.stock_status} for p in rows]}


def get_abandoned_carts(db: Session, merchant_id: uuid.UUID) -> dict:
    carts_df = load_carts_df(db, merchant_id)
    if carts_df.empty:
        return {"abandoned_sessions": 0}
    abandoned = carts_df[carts_df["status"] == "abandoned"]
    return {"abandoned_sessions": int(abandoned["id"].nunique())}


def get_campaign_performance(db: Session, merchant_id: uuid.UUID, campaign_id: uuid.UUID | None = None) -> dict:
    query = db.query(Campaign).filter(Campaign.merchant_id == merchant_id)
    if campaign_id:
        campaign = query.filter(Campaign.id == campaign_id).one_or_none()
        if not campaign:
            return {"found": False}
        campaigns = [campaign]
    else:
        campaigns = query.order_by(Campaign.created_at.desc()).limit(10).all()

    return {
        "found": True,
        "campaigns": [
            {
                "id": str(c.id), "name": c.name, "status": c.status,
                "expected_revenue_amount": float(c.expected_revenue_amount),
                "actual_revenue_amount": float(c.actual_revenue_amount),
            }
            for c in campaigns
        ],
    }


def get_payment_failure_metrics(db: Session, merchant_id: uuid.UUID) -> dict:
    orders_df = load_orders_df(db, merchant_id)
    metrics = compute_revenue_metrics(orders_df)
    return {"payment_failure_rate": metrics["payment_failure_rate"]}


def get_customer_profile(db: Session, merchant_id: uuid.UUID, customer_id: uuid.UUID) -> dict:
    customer = db.query(Customer).filter(Customer.merchant_id == merchant_id, Customer.id == customer_id).one_or_none()
    if not customer:
        return {"found": False, "reason": "no matching customer"}
    return {
        "found": True, "name": customer.name, "total_spend": float(customer.total_spend),
        "order_count": customer.order_count,
        "last_order_at": customer.last_order_at.isoformat() if customer.last_order_at else None,
    }


READ_TOOL_REGISTRY = {
    "get_revenue_metrics": get_revenue_metrics,
    "get_top_products": get_top_products,
    "get_customer_segments": get_customer_segments,
    "get_revenue_opportunities": get_revenue_opportunities,
    "get_product_details": get_product_details,
    "get_inventory": get_inventory,
    "get_abandoned_carts": get_abandoned_carts,
    "get_campaign_performance": get_campaign_performance,
    "get_payment_failure_metrics": get_payment_failure_metrics,
    "get_customer_profile": get_customer_profile,
}
