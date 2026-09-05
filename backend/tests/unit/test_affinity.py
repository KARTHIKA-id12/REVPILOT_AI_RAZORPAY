import uuid

import pandas as pd

from app.analytics.affinity import compute_product_affinity

PRODUCT_A = uuid.uuid4()  # e.g. Keyboard
PRODUCT_B = uuid.uuid4()  # e.g. Mouse
PRODUCT_C = uuid.uuid4()  # unrelated product


def _order_items(pairs: list[list], status: str = "paid") -> pd.DataFrame:
    """pairs: list of lists of product_ids representing one order's basket."""
    rows = []
    for basket in pairs:
        order_id = uuid.uuid4()
        for product_id in basket:
            rows.append({"order_id": order_id, "product_id": product_id, "quantity": 1, "unit_price_amount": 100.0, "status": status})
    return pd.DataFrame(rows)


def test_strong_affinity_produces_high_lift():
    # 20 orders: A+B together 15 times, A alone 5 times, B alone 5 times, C scattered
    baskets = [[PRODUCT_A, PRODUCT_B] for _ in range(15)]
    baskets += [[PRODUCT_A] for _ in range(5)]
    baskets += [[PRODUCT_B] for _ in range(5)]
    baskets += [[PRODUCT_C] for _ in range(20)]  # unrelated noise, no co-occurrence with A/B

    df = _order_items(baskets)
    affinity = compute_product_affinity(df, min_support_orders=1)

    row = affinity[(affinity["product_a"] == PRODUCT_A) & (affinity["product_b"] == PRODUCT_B)].iloc[0]
    assert row["count_both"] == 15
    assert row["count_a"] == 20  # 15 + 5
    assert row["confidence"] == round(15 / 20, 4)
    # lift > 1 confirms real positive association, not coincidence
    assert row["lift"] > 1.0


def test_unrelated_products_show_no_meaningful_affinity():
    baskets = [[PRODUCT_A] for _ in range(10)] + [[PRODUCT_C] for _ in range(10)]
    df = _order_items(baskets)
    affinity = compute_product_affinity(df, min_support_orders=1)
    # A and C never co-occur, so no row should exist for that pair
    pair = affinity[(affinity["product_a"] == PRODUCT_A) & (affinity["product_b"] == PRODUCT_C)]
    assert pair.empty


def test_min_support_threshold_filters_rare_pairs():
    baskets = [[PRODUCT_A, PRODUCT_B] for _ in range(2)] + [[PRODUCT_A] for _ in range(20)] + [[PRODUCT_B] for _ in range(20)]
    df = _order_items(baskets)
    affinity = compute_product_affinity(df, min_support_orders=5)
    pair = affinity[(affinity["product_a"] == PRODUCT_A) & (affinity["product_b"] == PRODUCT_B)]
    assert pair.empty  # only 2 co-occurrences, below the min_support_orders=5 threshold


def test_failed_orders_excluded_from_affinity():
    baskets = [[PRODUCT_A, PRODUCT_B] for _ in range(10)]
    df = _order_items(baskets, status="failed")
    affinity = compute_product_affinity(df, min_support_orders=1)
    assert affinity.empty
