from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_ok():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_never_leaks_secrets():
    response = client.get("/health")
    body = response.json()
    assert "database" in body
    assert "secret" not in str(body).lower()
    assert "key" not in str(body).lower() or body.get("payment_provider") in {"mock", "razorpay_test"}
