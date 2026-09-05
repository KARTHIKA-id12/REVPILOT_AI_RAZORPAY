import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from sqlalchemy.orm import Session

from app.analytics.affinity import compute_product_affinity
from app.analytics.metrics import compute_revenue_metrics, compute_revenue_trend, compute_top_products
from app.analytics.repository import (
    load_carts_df,
    load_customers_df,
    load_order_items_df,
    load_orders_df,
    load_products_df,
)
from app.analytics.rfm import compute_rfm, persist_rfm, summarize_segments
from app.models.campaigns import Campaign
from app.models.opportunities import RevenueOpportunity
from app.opportunities.scoring import (
    detect_abandoned_cart_opportunities,
    detect_cross_sell_and_bundle_opportunities,
    detect_reactivation_opportunities,
    detect_repeat_purchase_opportunities,
    score_opportunities,
)


def run_full_analytics(db: Session, merchant_id: uuid.UUID) -> dict:
    """The single entrypoint that runs the entire deterministic analytics
    pipeline for a merchant: load data -> compute metrics/RFM/affinity ->
    detect and score opportunities -> persist RFM + opportunities.
    Returns a summary dict for logging/CLI/API use."""
    now = datetime.now(UTC)

    orders_df = load_orders_df(db, merchant_id)
    order_items_df = load_order_items_df(db, merchant_id)
    customers_df = load_customers_df(db, merchant_id)
    products_df = load_products_df(db, merchant_id)
    carts_df = load_carts_df(db, merchant_id)

    metrics = compute_revenue_metrics(orders_df, carts_df)
    trend = compute_revenue_trend(orders_df)
    top_products = compute_top_products(order_items_df, products_df)

    rfm_df = compute_rfm(customers_df, orders_df, now)
    segment_summary = summarize_segments(rfm_df)
    persist_rfm(db, merchant_id, rfm_df, now)

    affinity_df = compute_product_affinity(order_items_df)

    candidates = []
    candidates += detect_cross_sell_and_bundle_opportunities(affinity_df, order_items_df, products_df)
    candidates += detect_abandoned_cart_opportunities(carts_df, products_df)
    candidates += detect_reactivation_opportunities(rfm_df, customers_df)
    candidates += detect_repeat_purchase_opportunities(order_items_df, products_df, now)

    scored = score_opportunities(candidates)

    # Idempotent: clear this merchant's OPEN opportunities before
    # re-inserting the freshly computed set, so re-running never
    # accumulates stale duplicates. Actioned/dismissed ones are preserved.
    # Defense in depth: also exclude any opportunity a campaign still
    # references, even if it's still marked 'open' for some reason (e.g.
    # a bug elsewhere, a manual edit) — deleting it would raise a foreign
    # key violation and abort the whole refresh. Better to skip it than
    # crash the analytics run.
    referenced_opportunity_ids = {
        row[0] for row in db.query(Campaign.opportunity_id).filter(
            Campaign.merchant_id == merchant_id, Campaign.opportunity_id.isnot(None)
        )
    }
    delete_query = db.query(RevenueOpportunity).filter(
        RevenueOpportunity.merchant_id == merchant_id, RevenueOpportunity.status == "open"
    )
    if referenced_opportunity_ids:
        delete_query = delete_query.filter(RevenueOpportunity.id.notin_(referenced_opportunity_ids))
    delete_query.delete(synchronize_session=False)

    for opp in scored:
        db.add(RevenueOpportunity(
            merchant_id=merchant_id,
            type=opp["type"],
            source_product_id=opp["source_product_id"],
            target_product_id=opp["target_product_id"],
            segment_id=None,  # segment_code is stored in evidence for now; FK link is a follow-up once segments are stable
            reach_count=opp["reach_count"],
            confidence=opp["confidence"],
            historical_affinity=opp["historical_affinity"],
            estimated_conversion=opp["estimated_conversion"],
            estimated_revenue_amount=opp["estimated_revenue_amount"],
            risk_level=opp["risk_level"],
            priority_score=opp["priority_score"],
            evidence_json={**opp["evidence_json"], "segment_code": opp["segment_code"]},
            status="open",
        ))

    db.commit()

    return {
        "metrics": metrics,
        "revenue_trend_points": len(trend),
        "top_products": top_products[:5],
        "segments": segment_summary,
        "opportunities_detected": len(scored),
        "opportunities_by_type": _count_by_type(scored),
    }


def _count_by_type(scored: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for opp in scored:
        counts[opp["type"]] = counts.get(opp["type"], 0) + 1
    return counts
