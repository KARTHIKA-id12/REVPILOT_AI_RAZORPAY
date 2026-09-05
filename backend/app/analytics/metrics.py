"""Deterministic revenue metrics. Every number here is computed from
orders/carts data passed in — never hard-coded, never estimated by an LLM.
Pure functions so they're trivially unit-testable with small DataFrames."""

import pandas as pd


def compute_revenue_metrics(orders_df: pd.DataFrame, carts_df: pd.DataFrame | None = None) -> dict:
    if orders_df.empty:
        return _empty_metrics()

    paid = orders_df[orders_df["status"] == "paid"]
    failed = orders_df[orders_df["status"] == "failed"]
    all_attempts = orders_df[orders_df["status"].isin(["paid", "failed", "cancelled"])]

    total_revenue = float(paid["total_amount"].sum())
    order_count = int(len(paid))
    aov = float(paid["total_amount"].mean()) if order_count else 0.0

    per_customer_order_counts = paid.groupby("customer_id").size()
    repeat_customers = int((per_customer_order_counts > 1).sum())
    total_purchasing_customers = int(len(per_customer_order_counts))
    repeat_purchase_rate = (repeat_customers / total_purchasing_customers) if total_purchasing_customers else 0.0

    payment_failure_rate = (len(failed) / len(all_attempts)) if len(all_attempts) else 0.0

    abandoned_cart_rate = None
    if carts_df is not None and not carts_df.empty:
        abandoned_sessions = carts_df.drop_duplicates("id")
        n_abandoned = int((abandoned_sessions["status"] == "abandoned").sum())
        n_checkout_opportunities = n_abandoned + order_count
        abandoned_cart_rate = (n_abandoned / n_checkout_opportunities) if n_checkout_opportunities else 0.0

    # Conversion rate: paid orders as a share of all checkout attempts
    # (paid + failed + cancelled + abandoned carts) — the fullest available
    # proxy for "did a shopping session end in revenue".
    denom = len(all_attempts) + (int((carts_df.drop_duplicates("id")["status"] == "abandoned").sum()) if carts_df is not None and not carts_df.empty else 0)
    conversion_rate = (order_count / denom) if denom else 0.0

    return {
        "total_revenue": round(total_revenue, 2),
        "order_count": order_count,
        "average_order_value": round(aov, 2),
        "conversion_rate": round(conversion_rate, 4),
        "repeat_purchase_rate": round(repeat_purchase_rate, 4),
        "payment_failure_rate": round(payment_failure_rate, 4),
        "abandoned_cart_rate": round(abandoned_cart_rate, 4) if abandoned_cart_rate is not None else None,
    }


def compute_revenue_trend(orders_df: pd.DataFrame, freq: str = "W") -> list[dict]:
    """Revenue bucketed by period (default weekly) for chart display."""
    if orders_df.empty:
        return []
    paid = orders_df[orders_df["status"] == "paid"].copy()
    if paid.empty:
        return []
    paid["created_at"] = pd.to_datetime(paid["created_at"])
    grouped = paid.set_index("created_at").resample(freq)["total_amount"].sum()
    return [{"period": str(period.date()), "revenue": round(float(value), 2)} for period, value in grouped.items()]


def compute_top_products(order_items_df: pd.DataFrame, products_df: pd.DataFrame, limit: int = 10) -> list[dict]:
    if order_items_df.empty:
        return []
    paid_items = order_items_df[order_items_df["status"] == "paid"].copy()
    paid_items["line_revenue"] = paid_items["quantity"] * paid_items["unit_price_amount"]
    by_product = paid_items.groupby("product_id").agg(revenue=("line_revenue", "sum"), units=("quantity", "sum"), orders=("order_id", "nunique"))
    merged = by_product.join(products_df.set_index("id")[["name", "sku"]], how="left").sort_values("revenue", ascending=False)
    return [
        {"product_id": str(idx), "name": row["name"], "sku": row["sku"], "revenue": round(float(row["revenue"]), 2), "units": int(row["units"]), "orders": int(row["orders"])}
        for idx, row in merged.head(limit).iterrows()
    ]


def _empty_metrics() -> dict:
    return {
        "total_revenue": 0.0, "order_count": 0, "average_order_value": 0.0,
        "conversion_rate": 0.0, "repeat_purchase_rate": 0.0,
        "payment_failure_rate": 0.0, "abandoned_cart_rate": None,
    }
