import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from main import app

VALID_PAYLOAD = {
    "latitude": 41.9028,
    "longitude": 12.4964,
    "accommodates": 4,
    "bedrooms": 2.0,
    "bathrooms": 1.5,
    "beds": 2,
    "room_type": "Entire home/apt",
}

RESPONSE_FIELDS = (
    "predicted_price_exact",
    "advisory_range_min",
    "advisory_range_max",
    "ab_variant",
    "client_ip",
    "current_prob_config",
    "prediction_time_ms",
)


def expected_variant(client_ip: str, target_probability: int) -> str:
    ip_hash = int(hashlib.md5(client_ip.encode("utf-8")).hexdigest(), 16)
    hash_bucket = ip_hash % 100
    return "A_Baseline" if hash_bucket >= target_probability else "B_Target"


def read_target_probability() -> int:
    with open("config.json") as f:
        return json.load(f).get("target_model_probability", 50)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolate_log_file(tmp_path, monkeypatch):
    """Redirects writes to logs_ab_test.jsonl to a temporary file,
    so that running the tests doesn't pollute the logs used by the evaluation notebook."""
    isolated_log_path = tmp_path / "logs_ab_test.jsonl"
    real_open = open

    def patched_open(file, *args, **kwargs):
        if file == "logs_ab_test.jsonl":
            return real_open(isolated_log_path, *args, **kwargs)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", patched_open)


def test_missing_required_fields_returns_422(client):
    response = client.post("/predict", json={"accommodates": 2})
    assert response.status_code == 422


def test_valid_request_returns_expected_response_shape(client):
    response = client.post(
        "/predict", json=VALID_PAYLOAD, headers={"X-Forwarded-For": "192.0.2.10"}
    )
    assert response.status_code == 200

    body = response.json()
    for field in RESPONSE_FIELDS:
        assert field in body
    assert body["ab_variant"] in ("A_Baseline", "B_Target")
    assert body["client_ip"] == "192.0.2.10"


def test_routing_is_sticky_for_the_same_ip(client):
    ip = "203.0.113.42"
    headers = {"X-Forwarded-For": ip}

    variants = {
        client.post("/predict", json=VALID_PAYLOAD, headers=headers).json()["ab_variant"]
        for _ in range(5)
    }
    assert len(variants) == 1, "The same IP address should always be routed to the same variant"


def test_routing_matches_md5_bucket_calculation(client):
    ip = "198.51.100.7"
    response = client.post("/predict", json=VALID_PAYLOAD, headers={"X-Forwarded-For": ip})

    assert response.json()["ab_variant"] == expected_variant(ip, read_target_probability())


def test_current_prob_config_reflects_config_file(client):
    response = client.post(
        "/predict", json=VALID_PAYLOAD, headers={"X-Forwarded-For": "192.0.2.55"}
    )
    assert response.json()["current_prob_config"] == read_target_probability()


def test_traffic_is_split_across_both_variants(client):
    ips = [f"203.0.113.{i}" for i in range(1, 60)]
    variants = {
        client.post("/predict", json=VALID_PAYLOAD, headers={"X-Forwarded-For": ip}).json()["ab_variant"]
        for ip in ips
    }
    assert variants == {"A_Baseline", "B_Target"}, "A pool of 59 different IPs should cover both variants"
