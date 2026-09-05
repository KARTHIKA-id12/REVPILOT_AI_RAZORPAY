import uuid

import pandas as pd

from app.analytics.metrics import compute_revenue_metrics, compute_top_products

CUSTOMER_A = uuid.uuid4()
CUSTOMER_B = uuid.uuid4()
CUSTOMER_C = uuid.uuid4()


def _orders_df():
    return pd.DataFrame([
        {"id": uuid.uuid4(), "customer_id": CUSTOMER_A, "status": "paid", "total_amount": 1000.0, "created_at": "2026-01-01"},
        {"id": uuid.uuid4(), "customer_id": CUSTOMER_A, "status": "paid", "total_amount": 2000.0, "created_at": "2026-02-01"},
        {"id": uuid.uuid4(), "customer_id": CUSTOMER_B, "status": "paid", "total_amount": 500.0, "created_at": "2026-01-15"},
        {"id": uuid.uuid4(), "customer_id": CUSTOMER_C, "status": "failed", "total_amount": 300.0, "created_at": "2026-01-20"},
        {"id": uuid.uuid4(), "customer_id": CUSTOMER_C, "status": "cancelled", "total_amount": 300.0, "created_at": "2026-01-21"},
    ])


def test_revenue_metrics_basic_math():
    metrics = compute_revenue_metrics(_orders_df())
    assert metrics["total_revenue"] == 3500.0
    assert metrics["order_count"] == 3
    assert metrics["average_order_value"] == round(3500.0 / 3, 2)


def test_repeat_purchase_rate():
    metrics = compute_revenue_metrics(_orders_df())
    # customer A has 2 paid orders (repeat), B has 1 -> 1/2 purchasing customers are repeat
    assert metrics["repeat_purchase_rate"] == 0.5


def test_payment_failure_rate():
    metrics = compute_revenue_metrics(_orders_df())
    # 1 failed out of (3 paid + 1 failed + 1 cancelled) = 5 attempts
    assert metrics["payment_failure_rate"] == round(1 / 5, 4)


def test_empty_orders_returns_zeroed_metrics_not_crash():
    metrics = compute_revenue_metrics(pd.DataFrame(columns=["id", "customer_id", "status", "total_amount", "created_at"]))
    assert metrics["total_revenue"] == 0.0
    assert metrics["order_count"] == 0


def test_top_products_ranks_by_revenue():
    product_a, product_b = uuid.uuid4(), uuid.uuid4()
    items = pd.DataFrame([
        {"order_id": uuid.uuid4(), "product_id": product_a, "quantity": 1, "unit_price_amount": 100.0, "status": "paid"},
        {"order_id": uuid.uuid4(), "product_id": product_a, "quantity": 1, "unit_price_amount": 100.0, "status": "paid"},
        {"order_id": uuid.uuid4(), "product_id": product_b, "quantity": 1, "unit_price_amount": 1000.0, "status": "paid"},
    ])
    products = pd.DataFrame([{"id": product_a, "name": "Cheap Thing", "sku": "A"}, {"id": product_b, "name": "Expensive Thing", "sku": "B"}])
    top = compute_top_products(items, products)
    assert top[0]["name"] == "Expensive Thing"
    assert top[0]["revenue"] == 1000.0
