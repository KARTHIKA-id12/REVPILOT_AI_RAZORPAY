"""Product affinity analysis: support, confidence, lift — computed from
real co-purchase data via a basket x product incidence matrix. This is
classic market-basket analysis (association rule mining), not ML, and not
an LLM guess. Every number is traceable back to actual paid orders."""

import numpy as np
import pandas as pd


def compute_product_affinity(order_items_df: pd.DataFrame, min_support_orders: int = 5) -> pd.DataFrame:
    """Returns one row per ordered (A, B) pair (both directions) with:
    count_a, count_b, count_both, n_orders, support, confidence (A->B), lift.
    """
    paid = order_items_df[order_items_df["status"] == "paid"]
    if paid.empty:
        return pd.DataFrame(columns=["product_a", "product_b", "count_a", "count_b", "count_both", "n_orders", "support", "confidence", "lift"])

    basket = paid.drop_duplicates(["order_id", "product_id"])
    incidence = pd.crosstab(basket["order_id"], basket["product_id"]).clip(upper=1)
    n_orders = int(incidence.shape[0])
    if n_orders == 0 or incidence.shape[1] < 2:
        return pd.DataFrame(columns=["product_a", "product_b", "count_a", "count_b", "count_both", "n_orders", "support", "confidence", "lift"])

    product_ids = incidence.columns.tolist()
    matrix = incidence.to_numpy(dtype=np.int64)
    co_occurrence = matrix.T @ matrix  # (products x products), diagonal = count of each product alone
    counts = np.diag(co_occurrence)

    rows = []
    for i, pid_a in enumerate(product_ids):
        for j, pid_b in enumerate(product_ids):
            if i == j:
                continue
            count_both = int(co_occurrence[i, j])
            if count_both < min_support_orders:
                continue
            count_a, count_b = int(counts[i]), int(counts[j])
            support = count_both / n_orders
            confidence = count_both / count_a if count_a else 0.0
            baseline_b = count_b / n_orders if n_orders else 0.0
            lift = (confidence / baseline_b) if baseline_b else 0.0
            rows.append({
                "product_a": pid_a, "product_b": pid_b,
                "count_a": count_a, "count_b": count_b, "count_both": count_both,
                "n_orders": n_orders, "support": round(support, 4),
                "confidence": round(confidence, 4), "lift": round(lift, 4),
            })

    return pd.DataFrame(rows, columns=["product_a", "product_b", "count_a", "count_b", "count_both", "n_orders", "support", "confidence", "lift"])


def top_affinity_pairs(affinity_df: pd.DataFrame, min_lift: float = 1.2, limit: int = 20) -> pd.DataFrame:
    if affinity_df.empty:
        return affinity_df
    filtered = affinity_df[affinity_df["lift"] >= min_lift]
    return filtered.sort_values("lift", ascending=False).head(limit)
