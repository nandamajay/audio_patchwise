import httpx


def test_health_endpoint_available() -> None:
    response = httpx.get("http://localhost:8000/health", timeout=10.0)
    assert response.status_code == 200
