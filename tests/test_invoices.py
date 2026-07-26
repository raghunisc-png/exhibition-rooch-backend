from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _login(test_agent):
    resp = client.post("/api/auth/login", json={"email": test_agent.email, "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_login_success(test_agent):
    token = _login(test_agent)
    assert token


def test_login_wrong_password(test_agent):
    resp = client.post("/api/auth/login", json={"email": test_agent.email, "password": "wrong"})
    assert resp.status_code == 401


def test_create_invoice_without_photo(test_agent):
    token = _login(test_agent)
    resp = client.post(
        "/api/invoices",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "client_uuid": "11111111-1111-1111-1111-111111111111",
            "customer_name": "Ada Lovelace",
            "customer_phone": "+919876543210",
            "product_name": "Smart Widget",
            "quantity": "2",
            "unit_price": "499.50",
            "tax_percent": "18",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["invoice_number"].startswith("INV-")
    assert body["subtotal"] == 999.0
    assert body["total"] > body["subtotal"]


def test_duplicate_client_uuid_is_idempotent(test_agent):
    token = _login(test_agent)
    payload = {
        "client_uuid": "22222222-2222-2222-2222-222222222222",
        "customer_name": "Grace Hopper",
        "customer_phone": "+919876500000",
        "product_name": "Widget Pro",
        "quantity": "1",
        "unit_price": "100",
    }
    resp1 = client.post("/api/invoices", headers={"Authorization": f"Bearer {token}"}, data=payload)
    resp2 = client.post("/api/invoices", headers={"Authorization": f"Bearer {token}"}, data=payload)
    assert resp1.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


def test_invalid_phone_rejected(test_agent):
    token = _login(test_agent)
    resp = client.post(
        "/api/invoices",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "client_uuid": "33333333-3333-3333-3333-333333333333",
            "customer_name": "Bad Phone",
            "customer_phone": "9876543210",  # missing +country code
            "product_name": "Widget",
        },
    )
    assert resp.status_code == 422


def test_sync_batch_idempotency(test_agent):
    token = _login(test_agent)
    item = {
        "client_uuid": "44444444-4444-4444-4444-444444444444",
        "customer_name": "Offline Customer",
        "customer_phone": "+919999999999",
        "product_name": "Booth Special",
        "quantity": 1,
        "unit_price": 250,
    }
    resp = client.post(
        "/api/sync/invoices",
        headers={"Authorization": f"Bearer {token}"},
        json={"items": [item, item]},  # same item twice in one batch
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    statuses = sorted(r["status"] for r in results)
    assert statuses == ["created", "duplicate"]
