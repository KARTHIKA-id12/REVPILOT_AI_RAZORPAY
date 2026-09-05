"""RFM (Recency, Frequency, Monetary) segmentation. Deterministic
rule-based scoring — no ML, no LLM. Quintile scoring uses rank-percentile
bucketing (robust to duplicate values, unlike raw pd.qcut) so it never
throws on skewed real-world data."""

import uuid
from datetime import datetime

import pandas as pd

SEGMENT_LABELS = {
    "champions": "Champions",
    "loyal": "Loyal Customers",
    "potential_loyalists": "Potential Loyalists",
    "new_customers": "New Customers",
    "at_risk": "At Risk",
    "dormant": "Dormant",
    "high_value": "High Value",
    "price_sensitive": "Price Sensitive",
    "needs_attention": "Needs Attention",
}

_SCORE_BINS = [0, 0.2, 0.4, 0.6, 0.8, 1.0]


def _percentile_score(series: pd.Series, ascending_is_better: bool) -> pd.Series:
    """1-5 score via min-max normalized rank. ascending_is_better=True means
    a larger raw value should get a larger score (frequency, monetary);
    False means a smaller raw value should get a larger score (recency —
    fewer days since last order is better). Uses (rank-1)/(n-1) rather than
    rank/n so the best and worst customers always land in the extreme
    bins, even with a small n — plain rank-percentile compresses toward
    the middle on small samples."""
    n = len(series)
    if n <= 1:
        return pd.Series([3] * n, index=series.index)  # not enough data to differentiate
    rank = series.rank(method="average", ascending=True)
    pct = (rank - 1) / (n - 1)
    if not ascending_is_better:
        pct = 1 - pct
    labels = [1, 2, 3, 4, 5]
    return pd.cut(pct, bins=_SCORE_BINS, labels=labels, include_lowest=True).astype(int)


def _assign_segment(row: pd.Series) -> str:
    r, f, m = row["r_score"], row["f_score"], row["m_score"]
    if r >= 4 and f >= 4 and m >= 4:
        return "champions"
    if f >= 4 and m >= 3:
        return "loyal"
    if f == 1 and r >= 4:
        return "new_customers"
    if r <= 2 and f >= 3:
        return "at_risk"
    if r <= 2 and f <= 2:
        return "dormant"
    if m == 5:
        return "high_value"
    if f >= 4 and m <= 2:
        return "price_sensitive"
    if r >= 3 and 2 <= f <= 3:
        return "potential_loyalists"
    return "needs_attention"


def compute_rfm(customers_df: pd.DataFrame, orders_df: pd.DataFrame, reference_date: datetime) -> pd.DataFrame:
    """Returns one row per customer WITH AT LEAST ONE PAID ORDER — a
    customer who never converted has no defined recency/frequency/
    monetary, so they're excluded rather than forced into a segment."""
    if orders_df.empty:
        return pd.DataFrame(columns=["customer_id", "recency_days", "frequency", "monetary", "r_score", "f_score", "m_score", "segment_code"])

    paid = orders_df[orders_df["status"] == "paid"].copy()
    if paid.empty:
        return pd.DataFrame(columns=["customer_id", "recency_days", "frequency", "monetary", "r_score", "f_score", "m_score", "segment_code"])

    paid["created_at"] = pd.to_datetime(paid["created_at"])
    if paid["created_at"].dt.tz is not None:
        paid["created_at"] = paid["created_at"].dt.tz_localize(None)
    ref = pd.Timestamp(reference_date).tz_localize(None) if pd.Timestamp(reference_date).tz else pd.Timestamp(reference_date)

    grouped = paid.groupby("customer_id").agg(
        last_order_at=("created_at", "max"),
        frequency=("id", "count"),
        monetary=("total_amount", "sum"),
    )
    grouped["recency_days"] = (ref - grouped["last_order_at"]).dt.days

    grouped["r_score"] = _percentile_score(grouped["recency_days"], ascending_is_better=False)
    grouped["f_score"] = _percentile_score(grouped["frequency"], ascending_is_better=True)
    grouped["m_score"] = _percentile_score(grouped["monetary"], ascending_is_better=True)

    grouped["segment_code"] = grouped.apply(_assign_segment, axis=1)
    grouped = grouped.reset_index().rename(columns={"customer_id": "customer_id"})
    return grouped[["customer_id", "recency_days", "frequency", "monetary", "r_score", "f_score", "m_score", "segment_code"]]


def summarize_segments(rfm_df: pd.DataFrame) -> list[dict]:
    if rfm_df.empty:
        return []
    summary = rfm_df.groupby("segment_code").agg(
        customer_count=("customer_id", "count"),
        total_revenue=("monetary", "sum"),
        avg_order_value=("monetary", lambda s: s.sum() / rfm_df.loc[s.index, "frequency"].sum()),
        avg_frequency=("frequency", "mean"),
    ).reset_index()
    return [
        {
            "segment_code": row["segment_code"],
            "label": SEGMENT_LABELS.get(row["segment_code"], row["segment_code"]),
            "customer_count": int(row["customer_count"]),
            "total_revenue": round(float(row["total_revenue"]), 2),
            "average_order_value": round(float(row["avg_order_value"]), 2),
            "average_frequency": round(float(row["avg_frequency"]), 2),
        }
        for _, row in summary.sort_values("total_revenue", ascending=False).iterrows()
    ]


def persist_rfm(db, merchant_id: uuid.UUID, rfm_df: pd.DataFrame, computed_at: datetime) -> None:
    """Writes segment definitions + per-customer memberships. Idempotent:
    clears prior memberships for this merchant's customers before
    re-inserting, so re-running analytics never duplicates rows."""
    from app.models.customers import CustomerSegment, CustomerSegmentMembership

    existing_segments = {s.code: s for s in db.query(CustomerSegment).filter(CustomerSegment.merchant_id == merchant_id)}
    for code, label in SEGMENT_LABELS.items():
        if code not in existing_segments:
            seg = CustomerSegment(merchant_id=merchant_id, code=code, label=label, definition_json={})
            db.add(seg)
            existing_segments[code] = seg
    db.flush()

    customer_ids = rfm_df["customer_id"].tolist() if not rfm_df.empty else []
    if customer_ids:
        db.query(CustomerSegmentMembership).filter(CustomerSegmentMembership.customer_id.in_(customer_ids)).delete(synchronize_session=False)

    for _, row in rfm_df.iterrows():
        db.add(CustomerSegmentMembership(
            customer_id=row["customer_id"],
            segment_id=existing_segments[row["segment_code"]].id,
            rfm_recency=int(row["r_score"]),
            rfm_frequency=int(row["f_score"]),
            rfm_monetary=int(row["m_score"]),
            computed_at=computed_at,
        ))
