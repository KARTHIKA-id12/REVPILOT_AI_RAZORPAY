import uuid

import pandas as pd

from app.opportunities.scoring import (
    detect_abandoned_cart_opportunities,
    detect_cross_sell_and_bundle_opportunities,
    detect_reactivation_opportunities,
    score_opportunities,
)

PRODUCT_A = uuid.uuid4()
PRODUCT_B = uuid.uuid4()


def _products_df():
    return pd.DataFrame([
        {"id": PRODUCT_A, "sku": "A", "name": "Keyboard", "price_amount": 3000.0, "stock_qty": 100, "stock_status": "in_stock", "category_id": None},
        {"id": PRODUCT_B, "sku": "B", "name": "Mouse", "price_amount": 1500.0, "stock_qty": 100, "stock_status": "in_stock", "category_id": None},
    ])


def _affinity_df():
    return pd.DataFrame([
        {"product_a": PRODUCT_A, "product_b": PRODUCT_B, "count_a": 100, "count_b": 60, "count_both": 40, "n_orders": 500, "support": 0.08, "confidence": 0.4, "lift": 3.3},
    ])


def _order_items_df():
    rows = []
    customers_both = [uuid.uuid4() for _ in range(40)]
    customers_a_only = [uuid.uuid4() for _ in range(60)]  # bought A but not B -> cross-sell reach
    for cid in customers_both:
        rows.append({"order_id": uuid.uuid4(), "product_id": PRODUCT_A, "customer_id": cid, "status": "paid"})
        rows.append({"order_id": uuid.uuid4(), "product_id": PRODUCT_B, "customer_id": cid, "status": "paid"})
    for cid in customers_a_only:
        rows.append({"order_id": uuid.uuid4(), "product_id": PRODUCT_A, "customer_id": cid, "status": "paid"})
    return pd.DataFrame(rows)


def test_cross_sell_reach_excludes_customers_who_already_bought_target():
    candidates = detect_cross_sell_and_bundle_opportunities(_affinity_df(), _order_items_df(), _products_df())
    assert len(candidates) == 1
    assert candidates[0].reach_count == 60  # only the A-only buyers, not the 40 who already have both


def test_high_support_pair_classified_as_bundle_not_cross_sell():
    candidates = detect_cross_sell_and_bundle_opportunities(_affinity_df(), _order_items_df(), _products_df(), bundle_support_threshold=0.05)
    assert candidates[0].type == "bundle"  # support=0.08 >= 0.05 threshold


def test_out_of_stock_target_forces_critical_risk():
    products = _products_df()
    products.loc[products["id"] == PRODUCT_B, "stock_status"] = "out_of_stock"
    candidates = detect_cross_sell_and_bundle_opportunities(_affinity_df(), _order_items_df(), products)
    assert candidates[0].risk_level == "critical"


def test_abandoned_cart_opportunity_needs_minimum_reach():
    small_carts = pd.DataFrame([
        {"id": uuid.uuid4(), "customer_id": uuid.uuid4(), "status": "abandoned", "product_id": PRODUCT_A, "quantity": 1, "unit_price_amount": 3000.0}
        for _ in range(3)  # below the reach>=5 threshold
    ])
    assert detect_abandoned_cart_opportunities(small_carts, _products_df()) == []

    big_carts = pd.DataFrame([
        {"id": uuid.uuid4(), "customer_id": uuid.uuid4(), "status": "abandoned", "product_id": PRODUCT_A, "quantity": 1, "unit_price_amount": 3000.0}
        for _ in range(10)
    ])
    candidates = detect_abandoned_cart_opportunities(big_carts, _products_df())
    assert len(candidates) == 1
    assert candidates[0].reach_count == 10
    assert "assumption" in candidates[0].evidence  # estimate must be clearly labeled


def test_reactivation_requires_high_value_at_risk_or_dormant_segment():
    rfm_df = pd.DataFrame([
        {"customer_id": uuid.uuid4(), "recency_days": 200, "frequency": 3, "monetary": 15000, "r_score": 1, "f_score": 3, "m_score": 5, "segment_code": "at_risk"}
        for _ in range(10)
    ] + [
        {"customer_id": uuid.uuid4(), "recency_days": 5, "frequency": 10, "monetary": 50000, "r_score": 5, "f_score": 5, "m_score": 5, "segment_code": "champions"}
        for _ in range(10)
    ])
    candidates = detect_reactivation_opportunities(rfm_df, pd.DataFrame())
    assert len(candidates) == 1
    assert candidates[0].reach_count == 10  # only the at_risk high-value ones, not the champions


def test_priority_score_normalized_0_to_100_and_ranked():
    candidates = detect_cross_sell_and_bundle_opportunities(_affinity_df(), _order_items_df(), _products_df())
    scored = score_opportunities(candidates)
    assert all(0 <= o["priority_score"] <= 100 for o in scored)
    assert scored == sorted(scored, key=lambda o: o["priority_score"], reverse=True)


def test_empty_candidates_returns_empty_list_not_error():
    assert score_opportunities([]) == []
