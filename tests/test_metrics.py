import pytest
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from app import main
from app.main import app
from app.metrics import (
    REQUEST_COUNT,
    REQUEST_DURATION,
    REQUESTS_IN_FLIGHT,
    resolve_route,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_metrics():
    REQUEST_COUNT.clear()
    REQUEST_DURATION.clear()
    REQUESTS_IN_FLIGHT.clear()

def test_metrics_endpoint_returns_prometheus_content_type():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST

def test_request_counter_records_route_template():
    client.get("/items/1")

    response = client.get("/metrics")

    assert (
        'http_requests_total{method="GET",route="/items/{item_id}",status="200"} 1.0'
        in response.text
    )

def test_metric_does_not_use_raw_path_as_route_label():
    client.get("/items/1")

    response = client.get("/metrics")

    assert "/items/1" not in response.text
    assert "/items/{item_id}" in response.text

def make_scope(method: str, path: str) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
    }

def test_resolve_route_returns_template_for_full_match():
    scope = make_scope("GET", "/items/1")

    route = resolve_route(scope, app.router.routes)

    assert route == "/items/{item_id}"

def test_resolve_route_returns_template_for_partial_match():
    scope = make_scope("POST", "/items/1")

    route = resolve_route(scope, app.router.routes)

    assert route == "/items/{item_id}"

def test_resolve_route_returns_fallback_for_unmatched_path():
    scope = make_scope("GET", "/does-not-exist")

    route = resolve_route(scope, app.router.routes)

    assert route == "__unmatched__"

def test_metrics_and_health_are_excluded_from_instrumentation():
    client.get("/health")
    client.get("/health/ready")
    client.get("/health/live")
    client.get("/metrics")

    response = client.get("/metrics")

    assert "http_requests_total{" not in response.text
    assert "http_request_duration_seconds_bucket{" not in response.text
    assert "http_requests_in_flight{" not in response.text
    
def test_http_500_is_recorded(monkeypatch):
    monkeypatch.setattr(main.chaos, "error_rate", 1.0)

    response = client.get("/items/1")

    assert response.status_code == 500

    metrics = client.get("/metrics").text

    assert (
        'http_requests_total{method="GET",route="/items/{item_id}",status="500"} 1.0'
        in metrics
    )

def test_in_flight_returns_to_zero_after_success():
    client.get("/items/1")

    metrics = client.get("/metrics").text

    assert (
        'http_requests_in_flight{method="GET",route="/items/{item_id}"} 0.0'
        in metrics
    )

def test_in_flight_returns_to_zero_after_error(monkeypatch):
    monkeypatch.setattr(main.chaos, "error_rate", 1.0)

    response = client.get("/items/1")

    assert response.status_code == 500

    metrics = client.get("/metrics").text

    assert (
        'http_requests_in_flight{method="GET",route="/items/{item_id}"} 0.0'
        in metrics
    )

def test_unmatched_path_is_not_used_as_route_label():
    client.get("/etc/passwd?q=../../secret")

    metrics = client.get("/metrics").text

    assert 'route="__unmatched__"' in metrics
    assert "/etc/passwd" not in metrics

def test_latency_histogram_uses_expected_buckets():
    client.get("/items/1")

    metrics = client.get("/metrics").text

    expected = [
        "0.01",
        "0.025",
        "0.05",
        "0.075",
        "0.1",
        "0.15",
        "0.2",
        "0.3",
        "0.4",
        "0.5",
        "0.75",
        "1.0",
        "1.5",
        "2.0",
        "+Inf",
    ]

    for bucket in expected:
        assert f'le="{bucket}"' in metrics