from __future__ import annotations

import time
import uuid

import httpx
import pytest


BASE_URL = "http://localhost:8000"


def _wait_for_checkout(client: httpx.Client, checkout_id: str, timeout_seconds: int = 15) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/checkout/{checkout_id}", timeout=2)
        if response.status_code == 200:
            body = response.json()
            if body["status"] in {"succeeded", "failed", "dead_lettered"}:
                return body
        time.sleep(1)
    return {}


def _wait_for_metrics(client: httpx.Client, timeout_seconds: int = 10) -> dict[str, int]:
    deadline = time.time() + timeout_seconds
    last = {}
    while time.time() < deadline:
        resp = client.get("/metrics", timeout=2)
        if resp.status_code == 200:
            last = resp.json()
            return last
        time.sleep(1)
    return last


@pytest.fixture()
def client() -> httpx.Client:
    try:
        health = httpx.get(f"{BASE_URL}/metrics", timeout=2)
        if health.status_code != 200:
            pytest.skip("API not reachable; start docker-compose first.")
    except httpx.HTTPError:
        pytest.skip("API not reachable; start docker-compose first.")
    return httpx.Client(base_url=BASE_URL, timeout=5.0)


def test_idempotency_same_payload_returns_same_checkout(client: httpx.Client) -> None:
    key = f"test-{uuid.uuid4()}"
    payload = {
        "customer_id": "cust_test",
        "items": [{"sku": "sku_123", "quantity": 1}],
        "payment_method": "card",
        "total_amount": 19.99,
        "inventory_mode": "none",
        "payment_mode": "none",
    }
    first = client.post("/checkout", headers={"Idempotency-Key": key}, json=payload)
    assert first.status_code == 200
    second = client.post("/checkout", headers={"Idempotency-Key": key}, json=payload)
    assert second.status_code == 200
    assert first.json()["checkout_id"] == second.json()["checkout_id"]


def test_idempotency_conflict_returns_409(client: httpx.Client) -> None:
    key = f"test-{uuid.uuid4()}"
    payload = {
        "customer_id": "cust_test",
        "items": [{"sku": "sku_123", "quantity": 1}],
        "payment_method": "card",
        "total_amount": 19.99,
        "inventory_mode": "none",
        "payment_mode": "none",
    }
    client.post("/checkout", headers={"Idempotency-Key": key}, json=payload)
    conflicting = {**payload, "total_amount": 29.99}
    conflict_response = client.post("/checkout", headers={"Idempotency-Key": key}, json=conflicting)
    assert conflict_response.status_code == 409


def test_metrics_success_increments(client: httpx.Client) -> None:
    before = _wait_for_metrics(client)
    key = f"test-{uuid.uuid4()}"
    payload = {
        "customer_id": "cust_test",
        "items": [{"sku": "sku_123", "quantity": 1}],
        "payment_method": "card",
        "total_amount": 24.99,
        "inventory_mode": "none",
        "payment_mode": "none",
    }
    response = client.post("/checkout", headers={"Idempotency-Key": key}, json=payload)
    assert response.status_code == 200
    body = _wait_for_checkout(client, response.json()["checkout_id"])
    assert body.get("status") == "succeeded"
    after = client.get("/metrics").json()
    assert after["success_count"] >= before.get("success_count", 0) + 1


def test_permanent_failure_dead_letters_and_counts(client: httpx.Client) -> None:
    before = _wait_for_metrics(client)
    key = f"test-{uuid.uuid4()}"
    payload = {
        "customer_id": "cust_test",
        "items": [{"sku": "sku_123", "quantity": 1}],
        "payment_method": "card",
        "total_amount": 24.99,
        "inventory_mode": "permanent",
        "payment_mode": "none",
    }
    response = client.post("/checkout", headers={"Idempotency-Key": key}, json=payload)
    assert response.status_code == 200
    body = _wait_for_checkout(client, response.json()["checkout_id"])
    assert body.get("status") == "dead_lettered"
    after = client.get("/metrics").json()
    assert after["failure_count"] >= before.get("failure_count", 0) + 1
