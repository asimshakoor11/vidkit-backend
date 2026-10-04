"""Health endpoint smoke test."""

from __future__ import annotations


def test_health_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
