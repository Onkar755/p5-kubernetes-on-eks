from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app, fizzbuzz

client = TestClient(app)


def test_health_returns_200_and_healthy_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.parametrize(
    "number, expected",
    [
        (9, "Fizz"),
        (10, "Buzz"),
        (15, "FizzBuzz"),
        (30, "FizzBuzz"),
        (7, 7),
        (0, "FizzBuzz"),
        (-9, "Fizz"),
    ],
)
def test_fizzbuzz_logic(number, expected):
    assert fizzbuzz(number) == expected


@pytest.mark.parametrize(
    "number, expected_result",
    [
        (9, "Fizz"),
        (10, "Buzz"),
        (15, "FizzBuzz"),
        (7, 7),
    ],
)
def test_fizzbuzz_endpoint_returns_200_and_expected_json(number, expected_result):
    response = client.get(f"/fizzbuzz/{number}")

    assert response.status_code == 200
    assert response.json() == {"number": number, "result": expected_result}


def test_fizzbuzz_endpoint_rejects_non_integer_path_param():
    response = client.get("/fizzbuzz/abc")

    assert response.status_code == 422


def test_count_endpoint_returns_incremented_value(monkeypatch):
    mock_incr = MagicMock(return_value=42)
    monkeypatch.setattr(main.redis_client, "incr", mock_incr)

    response = client.get("/count")

    assert response.status_code == 200
    assert response.json() == {"count": 42}
    mock_incr.assert_called_once_with("count")
