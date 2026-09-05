import uuid
from datetime import datetime, timedelta

import pandas as pd

from app.analytics.rfm import compute_rfm

REFERENCE = datetime(2026, 8, 21)


def _make_customer_orders(customer_id, n_orders, days_ago_last, amount_each):
    """n_orders spread out, most recent `days_ago_last` days before REFERENCE."""
    rows = []
    for i in range(n_orders):
        days_ago = days_ago_last + i * 10
        rows.append({
            "id": uuid.uuid4(), "customer_id": customer_id, "status": "paid",
            "total_amount": amount_each, "created_at": REFERENCE - timedelta(days=days_ago),
        })
    return rows


def test_frequent_recent_big_spender_is_champion():
    champion = uuid.uuid4()
    dormant = uuid.uuid4()
    occasional = uuid.uuid4()

    rows = []
    rows += _make_customer_orders(champion, n_orders=10, days_ago_last=2, amount_each=5000)
    rows += _make_customer_orders(dormant, n_orders=1, days_ago_last=300, amount_each=500)
    rows += _make_customer_orders(occasional, n_orders=3, days_ago_last=100, amount_each=1500)

    orders_df = pd.DataFrame(rows)
    rfm = compute_rfm(pd.DataFrame(), orders_df, REFERENCE)

    champion_row = rfm[rfm["customer_id"] == champion].iloc[0]
    assert champion_row["segment_code"] == "champions"
    assert champion_row["r_score"] == 5
    assert champion_row["f_score"] == 5


def test_customers_with_no_orders_are_excluded_not_fabricated():
    orders_df = pd.DataFrame(columns=["id", "customer_id", "status", "total_amount", "created_at"])
    rfm = compute_rfm(pd.DataFrame(), orders_df, REFERENCE)
    assert rfm.empty


def test_dormant_customer_detected_by_low_recency_and_frequency():
    champion = uuid.uuid4()
    dormant = uuid.uuid4()
    rows = []
    rows += _make_customer_orders(champion, n_orders=10, days_ago_last=2, amount_each=5000)
    rows += _make_customer_orders(dormant, n_orders=1, days_ago_last=340, amount_each=500)
    orders_df = pd.DataFrame(rows)

    rfm = compute_rfm(pd.DataFrame(), orders_df, REFERENCE)
    dormant_row = rfm[rfm["customer_id"] == dormant].iloc[0]
    assert dormant_row["r_score"] == 1
    assert dormant_row["segment_code"] in {"dormant", "at_risk"}
