"""Revenue opportunity detection. Every opportunity here is built from
real computed signal (affinity, RFM segments, inventory, abandoned carts)
— nothing is invented. Where a number is a projection rather than an
observed fact (e.g. an assumed conversion rate for a campaign that hasn't
run yet), it's clearly tagged as an assumption in evidence_json so the UI
can label it ESTIMATED rather than implying certainty.

Covers 5 of the 8 opportunity types from the product spec now
(cross_sell, bundle, abandoned_cart, reactivation, repeat_purchase).
upsell, retention, and inventory_aware are natural extensions of this same
pattern — left as documented follow-ups rather than padded out with
low-signal filler.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

# Conservative, explicitly-labeled assumptions used only where no organic
# conversion signal exists yet (e.g. abandoned-cart recovery rate). These
# are industry-typical ballpark figures, not fabricated precision — always
# surfaced as ESTIMATED in evidence, never presented as measured fact.
ASSUMED_ABANDONED_CART_RECOVERY_RATE = 0.12
ASSUMED_REACTIVATION_RATE = 0.08
ASSUMED_REPEAT_PURCHASE_RATE = 0.15
CAMPAIGN_RESPONSE_DAMPENER = 0.6  # organic affinity confidence overstates a *targeted* campaign's response


@dataclass
class OpportunityCandidate:
    type: str
    source_product_id: uuid.UUID | None
    target_product_id: uuid.UUID | None
    segment_code: str | None
    reach_count: int
    confidence: float
    historical_affinity: float  # lift, or 0 if not affinity-based
    estimated_conversion: float
    estimated_revenue_amount: float
    risk_level: str
    evidence: dict = field(default_factory=dict)


def _stock_status_of(products_df: pd.DataFrame, product_id) -> str:
    row = products_df[products_df["id"] == product_id]
    return row.iloc[0]["stock_status"] if not row.empty else "unknown"


def _price_of(products_df: pd.DataFrame, product_id) -> float:
    row = products_df[products_df["id"] == product_id]
    return float(row.iloc[0]["price_amount"]) if not row.empty else 0.0


def _risk_for_stock(stock_status: str, lift: float) -> str:
    if stock_status == "out_of_stock":
        return "critical"
    if stock_status == "low_stock":
        return "high"
    if lift >= 2.0:
        return "low"
    if lift >= 1.4:
        return "medium"
    return "high"


def detect_cross_sell_and_bundle_opportunities(
    affinity_df: pd.DataFrame, order_items_df: pd.DataFrame, products_df: pd.DataFrame,
    bundle_support_threshold: float = 0.04, min_lift: float = 1.2,
) -> list[OpportunityCandidate]:
    if affinity_df.empty:
        return []

    paid_items = order_items_df[order_items_df["status"] == "paid"]
    candidates = []

    for _, row in affinity_df[affinity_df["lift"] >= min_lift].iterrows():
        product_a, product_b = row["product_a"], row["product_b"]

        customers_a = set(paid_items[paid_items["product_id"] == product_a]["customer_id"])
        customers_b = set(paid_items[paid_items["product_id"] == product_b]["customer_id"])
        reach = customers_a - customers_b
        if len(reach) < 5:
            continue

        stock_status = _stock_status_of(products_df, product_b)
        price_b = _price_of(products_df, product_b)
        estimated_conversion = round(min(0.6, row["confidence"] * CAMPAIGN_RESPONSE_DAMPENER), 4)
        estimated_revenue = round(len(reach) * estimated_conversion * price_b, 2)

        opp_type = "bundle" if row["support"] >= bundle_support_threshold else "cross_sell"

        candidates.append(OpportunityCandidate(
            type=opp_type,
            source_product_id=product_a,
            target_product_id=product_b,
            segment_code=None,
            reach_count=len(reach),
            confidence=min(0.99, round((row["lift"] - 1) / 2, 4)) if row["lift"] > 1 else 0.0,
            historical_affinity=float(row["lift"]),
            estimated_conversion=estimated_conversion,
            estimated_revenue_amount=estimated_revenue,
            risk_level=_risk_for_stock(stock_status, row["lift"]),
            evidence={
                "customers_bought_source": int(row["count_a"]),
                "customers_bought_both": int(row["count_both"]),
                "support": float(row["support"]),
                "confidence_organic": float(row["confidence"]),
                "lift": float(row["lift"]),
                "target_stock_status": stock_status,
                "assumption": f"Estimated conversion = organic confidence x {CAMPAIGN_RESPONSE_DAMPENER} "
                "(a targeted campaign is assumed to convert at a discount to naturally observed co-purchase rate).",
            },
        ))

    return candidates


def detect_abandoned_cart_opportunities(carts_df: pd.DataFrame, products_df: pd.DataFrame) -> list[OpportunityCandidate]:
    if carts_df.empty:
        return []
    abandoned = carts_df[carts_df["status"] == "abandoned"]
    if abandoned.empty:
        return []

    candidates = []
    for product_id, group in abandoned.groupby("product_id"):
        reach = int(group["id"].nunique())
        if reach < 5:
            continue
        price = _price_of(products_df, product_id)
        stock_status = _stock_status_of(products_df, product_id)
        estimated_revenue = round(reach * ASSUMED_ABANDONED_CART_RECOVERY_RATE * price, 2)

        candidates.append(OpportunityCandidate(
            type="abandoned_cart",
            source_product_id=None,
            target_product_id=product_id,
            segment_code=None,
            reach_count=reach,
            confidence=0.5,
            historical_affinity=0.0,
            estimated_conversion=ASSUMED_ABANDONED_CART_RECOVERY_RATE,
            estimated_revenue_amount=estimated_revenue,
            risk_level=_risk_for_stock(stock_status, 1.5),
            evidence={
                "abandoned_sessions": reach,
                "assumption": f"Recovery rate assumed at {ASSUMED_ABANDONED_CART_RECOVERY_RATE:.0%} "
                "(industry-typical cart-recovery-email benchmark, not yet measured for this merchant).",
                "target_stock_status": stock_status,
            },
        ))
    return candidates


def detect_reactivation_opportunities(rfm_df: pd.DataFrame, customers_df: pd.DataFrame) -> list[OpportunityCandidate]:
    if rfm_df.empty:
        return []
    target = rfm_df[rfm_df["segment_code"].isin(["at_risk", "dormant"]) & (rfm_df["m_score"] >= 4)]
    if len(target) < 5:
        return []

    reach = int(len(target))
    avg_historical_order_value = float(target["monetary"].sum() / target["frequency"].sum())
    estimated_revenue = round(reach * ASSUMED_REACTIVATION_RATE * avg_historical_order_value, 2)

    return [OpportunityCandidate(
        type="reactivation",
        source_product_id=None,
        target_product_id=None,
        segment_code="at_risk_high_value",
        reach_count=reach,
        confidence=0.4,
        historical_affinity=0.0,
        estimated_conversion=ASSUMED_REACTIVATION_RATE,
        estimated_revenue_amount=estimated_revenue,
        risk_level="medium",
        evidence={
            "segment_customer_count": reach,
            "avg_historical_order_value": round(avg_historical_order_value, 2),
            "assumption": f"Reactivation rate assumed at {ASSUMED_REACTIVATION_RATE:.0%} "
            "(win-back campaign benchmark; this merchant has not run one yet).",
        },
    )]


def detect_repeat_purchase_opportunities(
    order_items_df: pd.DataFrame, products_df: pd.DataFrame, reference_date: datetime, min_days_since: int = 60,
) -> list[OpportunityCandidate]:
    paid = order_items_df[order_items_df["status"] == "paid"].copy()
    if paid.empty:
        return []
    paid["created_at"] = pd.to_datetime(paid["created_at"])
    if paid["created_at"].dt.tz is not None:
        paid["created_at"] = paid["created_at"].dt.tz_localize(None)
    ref = pd.Timestamp(reference_date).tz_localize(None) if pd.Timestamp(reference_date).tz else pd.Timestamp(reference_date)

    candidates = []
    for product_id, group in paid.groupby("product_id"):
        per_customer_purchases = group.groupby("customer_id")["created_at"].agg(["count", "max"])
        single_buyers = per_customer_purchases[per_customer_purchases["count"] == 1]
        eligible = single_buyers[(ref - single_buyers["max"]).dt.days >= min_days_since]
        reach = int(len(eligible))
        if reach < 8:
            continue

        price = _price_of(products_df, product_id)
        stock_status = _stock_status_of(products_df, product_id)
        estimated_revenue = round(reach * ASSUMED_REPEAT_PURCHASE_RATE * price, 2)

        candidates.append(OpportunityCandidate(
            type="repeat_purchase",
            source_product_id=product_id,
            target_product_id=product_id,
            segment_code=None,
            reach_count=reach,
            confidence=0.35,
            historical_affinity=0.0,
            estimated_conversion=ASSUMED_REPEAT_PURCHASE_RATE,
            estimated_revenue_amount=estimated_revenue,
            risk_level=_risk_for_stock(stock_status, 1.5),
            evidence={
                "one_time_buyers_overdue_for_reorder": reach,
                "min_days_since_last_purchase": min_days_since,
                "assumption": f"Reorder response rate assumed at {ASSUMED_REPEAT_PURCHASE_RATE:.0%}.",
                "target_stock_status": stock_status,
            },
        ))
    return candidates


def score_opportunities(candidates: list[OpportunityCandidate]) -> list[dict]:
    """Normalizes priority_score to 0-100 across the candidate set using
    the spec's formula: revenue_potential x confidence x reach x
    availability x historical_conversion x margin_safety — each factor
    normalized to [0,1] before multiplying, then the product is min-max
    scaled to 0-100 across all candidates so scores are comparable."""
    if not candidates:
        return []

    max_revenue = max((c.estimated_revenue_amount for c in candidates), default=1) or 1
    max_reach = max((c.reach_count for c in candidates), default=1) or 1

    raw_scores = []
    for c in candidates:
        revenue_factor = c.estimated_revenue_amount / max_revenue
        reach_factor = c.reach_count / max_reach
        availability_factor = {"low": 1.0, "medium": 0.85, "high": 0.6, "critical": 0.1}.get(_availability_bucket(c), 0.5)
        conversion_factor = min(1.0, c.estimated_conversion / 0.3)  # 30%+ conversion treated as ceiling
        margin_safety_factor = 1.0  # no COGS data yet; treated as neutral until Phase-later cost modeling exists
        raw = revenue_factor * max(c.confidence, 0.1) * reach_factor * availability_factor * conversion_factor * margin_safety_factor
        raw_scores.append(raw)

    max_raw = max(raw_scores) or 1
    results = []
    for c, raw in zip(candidates, raw_scores, strict=True):
        priority_score = round((raw / max_raw) * 100, 2)
        results.append({
            "type": c.type,
            "source_product_id": c.source_product_id,
            "target_product_id": c.target_product_id,
            "segment_code": c.segment_code,
            "reach_count": c.reach_count,
            "confidence": c.confidence,
            "historical_affinity": c.historical_affinity,
            "estimated_conversion": c.estimated_conversion,
            "estimated_revenue_amount": c.estimated_revenue_amount,
            "risk_level": c.risk_level,
            "priority_score": priority_score,
            "evidence_json": c.evidence,
        })
    return sorted(results, key=lambda r: r["priority_score"], reverse=True)


def _availability_bucket(c: OpportunityCandidate) -> str:
    return c.risk_level if c.risk_level in {"low", "medium", "high", "critical"} else "medium"
