import inspect

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import LATENCY_MAX_S, LATENCY_MIN_S, app, _draw_latency

client = TestClient(app)


def _no_latency(monkeypatch):
    monkeypatch.setattr(main, "_draw_latency", lambda multiplier: 0.0)
    monkeypatch.setattr(main.chaos, "error_rate", 0.0)
    monkeypatch.setattr(main.chaos, "latency_multiplier", 1.0)
    monkeypatch.setattr(main.chaos, "ready", True)
    monkeypatch.setattr(main.chaos, "alive", True)


@pytest.mark.parametrize("item_id", [1, 42, 999999999, 0, -7])
def test_items_endpoint_returns_200_and_item_body(monkeypatch, item_id):
    _no_latency(monkeypatch)

    response = client.get(f"/items/{item_id}")

    assert response.status_code == 200
    assert response.json() == {"item_id": item_id, "name": f"item-{item_id}"}


def test_items_endpoint_rejects_non_integer_path_param():
    response = client.get("/items/abc")

    assert response.status_code == 422


def test_items_endpoint_returns_500_when_error_rate_is_one(monkeypatch):
    _no_latency(monkeypatch)
    monkeypatch.setattr(main.chaos, "error_rate", 1.0)

    response = client.get("/items/1")

    assert response.status_code == 500


def test_items_endpoint_returns_200_when_error_rate_is_zero(monkeypatch):
    _no_latency(monkeypatch)
    monkeypatch.setattr(main.chaos, "error_rate", 0.0)

    response = client.get("/items/1")

    assert response.status_code == 200


def test_items_endpoint_is_a_coroutine_function():
    # Proves ONLY that the handler is `async def`, so FastAPI runs it on the
    # event loop rather than in the threadpool. It does NOT prove the handler
    # avoids blocking calls -- an `async def` body containing `time.sleep()`
    # passes this test while serialising every request. The concurrent-load
    # wall-clock check in the README is the actual evidence for non-blocking
    # behaviour; this is a cheap structural guard, not a proof.
    assert inspect.iscoroutinefunction(main.get_item)


def test_admin_chaos_returns_defaults():
    response = client.get("/admin/chaos")

    assert response.status_code == 200
    assert response.json() == {
        "error_rate": 0.0,
        "latency_multiplier": 1.0,
        "ready": True,
        "alive": True,
    }


def test_admin_chaos_put_round_trips_config_change(monkeypatch):
    monkeypatch.setattr(main.chaos, "error_rate", 0.0)
    monkeypatch.setattr(main.chaos, "latency_multiplier", 1.0)
    new_config = new_config = {
        "error_rate": 0.25,
        "latency_multiplier": 3.0,
        "ready": False,
        "alive": True,
    }

    put_response = client.put("/admin/chaos", json=new_config)
    get_response = client.get("/admin/chaos")

    assert put_response.status_code == 200
    assert put_response.json() == new_config
    assert get_response.status_code == 200
    assert get_response.json() == new_config


@pytest.mark.parametrize(
    "partial_body",
    [
        {"error_rate": 0.5},
        {"latency_multiplier": 2.0},
        {"ready": False},
        {"alive": False},
        {
            "error_rate": 0.5,
            "latency_multiplier": 2.0,
            "ready": True,
        },
        {},
    ],
)
def test_admin_chaos_put_rejects_partial_body(monkeypatch, partial_body):
    monkeypatch.setattr(main.chaos, "error_rate", 0.4)
    monkeypatch.setattr(main.chaos, "latency_multiplier", 2.5)
    monkeypatch.setattr(main.chaos, "ready", True)
    monkeypatch.setattr(main.chaos, "alive", True)

    response = client.put("/admin/chaos", json=partial_body)

    assert response.status_code == 422
    # A rejected update must not move the field it did not mention.
    assert client.get("/admin/chaos").json() == {
        "error_rate": 0.4,
        "latency_multiplier": 2.5,
        "ready": True,
        "alive": True,
    }


@pytest.mark.parametrize(
    "error_rate, latency_multiplier",
    [(-0.1, 1.0), (1.5, 1.0), (0.0, 0.0), (0.0, -1.0)],
)
def test_admin_chaos_put_rejects_out_of_range_values(error_rate, latency_multiplier):
    response = client.put(
        "/admin/chaos",
        json={
            "error_rate": error_rate,
            "latency_multiplier": latency_multiplier,
            "ready": True,
            "alive": True,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("multiplier", [0.5, 1.0, 10.0])
def test_draw_latency_respects_bounds_and_multiplier(multiplier):
    draws = [_draw_latency(multiplier) for _ in range(200)]

    assert all(
        LATENCY_MIN_S * multiplier <= d <= LATENCY_MAX_S * multiplier for d in draws
    )
