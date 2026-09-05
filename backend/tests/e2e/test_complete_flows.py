"""Phase 22 API-level end-to-end smoke flows.

The fixtures intentionally come from the integration suites so the E2E layer
starts from realistic merchant data and still owns the browser-facing request
sequence. The suite skips cleanly when PostgreSQL is not available locally.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_merchant_console_flow_is_wired_end_to_end(full_loop_merchant):
    _db, merchant_id, _source_id, _target_id, _opportunity_id = full_loop_merchant

    dashboard = client.get(f"/api/v1/dashboard/summary?merchant_id={merchant_id}")
    assert dashboard.status_code == 200
    assert "total_revenue" in dashboard.json()

    customers = client.get(f"/api/v1/merchant/customers?merchant_id={merchant_id}")
    products = client.get(f"/api/v1/merchant/products?merchant_id={merchant_id}")
    assert customers.status_code == 200 and customers.json()["total"] >= 1
    assert products.status_code == 200 and products.json()["total"] >= 2

    session = client.post("/api/v1/agent/sessions", json={"merchant_id": str(merchant_id)})
    assert session.status_code == 200
    session_id = session.json()["id"]

    message = client.post(
        f"/api/v1/agent/sessions/{session_id}/messages?merchant_id={merchant_id}",
        json={"content": "What's my top revenue opportunity?"},
    )
    assert message.status_code == 200
    assert message.json()["intent"] == "VIEW_OPPORTUNITIES"

    traces = client.get(f"/api/v1/ops/traces?merchant_id={merchant_id}")
    assert traces.status_code == 200
    assert traces.json()["total"] >= 1


def test_ai_buyer_checkout_flow_is_wired_end_to_end(buyer_cart):
    _db, merchant_id, _product_id, _cart_id, session_ref = buyer_cart

    preview = client.post(
        "/api/v1/agent/checkout/preview",
        json={"merchant_id": str(merchant_id), "session_ref": session_ref},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["preview_id"]
    assert preview_body["total"]["amount"] > 0

    confirmed = client.post(
        "/api/v1/agent/checkout/confirm",
        json={
            "merchant_id": str(merchant_id), "session_ref": session_ref,
            "preview_id": preview_body["preview_id"], "confirmed": True,
            "buyer_name": "E2E Buyer", "buyer_email": "e2e@example.com",
        },
    )
    assert confirmed.status_code == 200
    order_id = confirmed.json()["order_id"]

    verified = client.post(
        "/api/v1/agent/checkout/verify",
        json={"merchant_id": str(merchant_id), "order_id": order_id, "demo": True},
    )
    assert verified.status_code == 200
    assert verified.json()["payment_status"] == "paid"