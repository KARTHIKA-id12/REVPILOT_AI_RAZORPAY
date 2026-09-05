"""Resolves the real inputs a campaign simulation needs (reach, AOV,
organic confidence) from live transaction data or a stored opportunity.
This is deliberately the ONLY place this logic lives — both the agent's
SIMULATE_CAMPAIGN tool (app/agents/pipeline.py) and the standalone
Simulator API (app/api/simulations.py) call this, so there is exactly one
implementation to keep correct rather than two that could silently drift
apart and disagree with each other."""

import uuid

from sqlalchemy.orm import Session

from app.analytics.repository import load_order_items_df, load_orders_df
from app.models.catalog import Product
from app.models.opportunities import RevenueOpportunity


def compute_simulation_inputs(db: Session, merchant_id: uuid.UUID, product_ids: list[uuid.UUID]) -> dict:
    """Recomputes reach/AOV/organic_confidence from live transaction data.
    Never trusts a number from a request payload — this is the ONLY
    source of truth for simulation inputs."""
    order_items_df = load_order_items_df(db, merchant_id)
    orders_df = load_orders_df(db, merchant_id)
    paid_items = order_items_df[order_items_df["status"] == "paid"] if not order_items_df.empty else order_items_df
    paid_orders = orders_df[orders_df["status"] == "paid"] if not orders_df.empty else orders_df

    if len(product_ids) >= 2 and not paid_items.empty:
        source_id, target_id = product_ids[0], product_ids[1]
        if source_id == target_id:
            customers = set(paid_items[paid_items["product_id"] == source_id]["customer_id"])
            reach = len(customers)
            organic_confidence = 0.35
        else:
            customers_source = set(paid_items[paid_items["product_id"] == source_id]["customer_id"])
            customers_target = set(paid_items[paid_items["product_id"] == target_id]["customer_id"])
            reach = len(customers_source - customers_target)
            organic_confidence = (len(customers_source & customers_target) / len(customers_source)) if customers_source else 0.0
    elif not paid_items.empty:
        customers = set(paid_items[paid_items["product_id"] == product_ids[0]]["customer_id"])
        reach = len(customers)
        organic_confidence = 0.3  # no natural pair to derive confidence from — documented conservative default
    else:
        reach, organic_confidence = 0, 0.0

    target_product = db.get(Product, product_ids[-1]) if product_ids else None
    if target_product:
        aov = float(target_product.price_amount)
    elif not paid_orders.empty:
        aov = float(paid_orders["total_amount"].mean())
    else:
        aov = 0.0

    return {"eligible_customers": reach, "average_order_value": aov, "organic_confidence": organic_confidence}


def resolve_product_ids_and_confidence(db: Session, merchant_id: uuid.UUID, *, opportunity_id: uuid.UUID | None, product_ids: list[uuid.UUID] | None) -> dict:
    """Given either an opportunity_id or an explicit product list, returns
    the real product_ids plus the simulation inputs to run against. When
    an opportunity is given, its stored evidence (already computed by the
    Phase 4 analytics engine from real transactions) is preferred over
    re-deriving from scratch — it's the same fact, computed once."""
    if opportunity_id:
        opportunity = db.get(RevenueOpportunity, opportunity_id)
        if not opportunity or opportunity.merchant_id != merchant_id:
            return {"found": False}
        resolved_product_ids = [p for p in [opportunity.source_product_id, opportunity.target_product_id] if p]
        if not resolved_product_ids:
            return {"found": False}
        
        target_product = db.get(Product, resolved_product_ids[-1]) if resolved_product_ids else None
        aov = float(target_product.price_amount) if target_product else 0.0

        return {
            "found": True,
            "product_ids": resolved_product_ids,
            "eligible_customers": opportunity.reach_count,
            "average_order_value": aov,
            "organic_confidence": float(opportunity.confidence)
        }

    if product_ids:
        inputs = compute_simulation_inputs(db, merchant_id, product_ids)
        return {"found": True, "product_ids": product_ids, **inputs}

    return {"found": False}
