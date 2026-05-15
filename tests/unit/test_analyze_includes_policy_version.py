"""analyze 응답에 policy_version 키가 포함되는지 확인."""
from collections import deque

from fastapi.testclient import TestClient

from ml_server.main import app
from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest
from ml_server.policy import reload_policies, get_scoring_policy


def _metrics():
    return MetricsRequest(
        pc_id="pc-pv", timestamp="2026-05-04T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )


def test_analyze_pattern_returns_policy_version():
    reload_policies()
    result = analyze_pattern(_metrics(), deque(), slot="class")
    assert "policy_version" in result
    assert result["policy_version"] == get_scoring_policy().version


def test_analyze_endpoint_returns_policy_version():
    reload_policies()
    with TestClient(app) as client:
        resp = client.post("/analyze", json=_metrics().model_dump())
        assert resp.status_code == 200
        body = resp.json()
        assert "policy_version" in body
        assert body["policy_version"] == get_scoring_policy().version
