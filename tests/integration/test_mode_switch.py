"""mode=mlserver vs mode=springboot 분기 통합 검증."""
from __future__ import annotations

import pytest
import requests

from agent_core.config.loader import AgentConfig, load_config
from agent_core.sender import MetricsSender


class _FakeResp:
    status_code = 200

    def json(self):
        return {"ok": True}


@pytest.fixture
def capture_post(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["payload"] = json
        return _FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    return captured


def test_mode_mlserver_routes_to_analyze(capture_post):
    cfg = AgentConfig(
        mode="mlserver",
        ml_server_url="http://ml:8000/analyze",
        spring_boot_url="http://sb:8080/api/metrics",
    )
    sender = MetricsSender(config=cfg)
    sender.send({"pc_id": "x", "timestamp": "t"}, [], {})
    assert capture_post["url"].endswith("/analyze")
    assert "X-API-Key" not in capture_post["headers"]


def test_mode_springboot_routes_to_api_metrics(capture_post):
    cfg = AgentConfig(
        mode="springboot",
        ml_server_url="http://ml:8000/analyze",
        spring_boot_url="http://sb:8080/api/metrics",
        api_key="K",
    )
    sender = MetricsSender(config=cfg)
    sender.send({"pc_id": "x", "timestamp": "t"}, [], {})
    assert capture_post["url"].endswith("/api/metrics")
    assert capture_post["headers"].get("X-API-Key") == "K"
    assert capture_post["headers"].get("Content-Type") == "application/json"


def test_env_override_switches_mode(monkeypatch, capture_post):
    monkeypatch.setenv("RADA_MODE", "mlserver")
    monkeypatch.setenv("RADA_ML_SERVER_URL", "http://envml:8000/analyze")
    cfg = load_config()
    sender = MetricsSender(config=cfg)
    sender.send({"pc_id": "x", "timestamp": "t"}, [], {})
    assert capture_post["url"] == "http://envml:8000/analyze"
    assert "X-API-Key" not in capture_post["headers"]


def test_url_routing_through_config(monkeypatch):
    """기존 회귀: 직접 url 지정 시 해당 url 로 호출."""
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["payload_keys"] = list((json or {}).keys())
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)

    sender_ml = MetricsSender(url="http://ml-server:8000/analyze")
    sender_ml.send({"pc_id": "x", "timestamp": "t"}, [], {})
    assert captured["url"] == "http://ml-server:8000/analyze"

    sender_spring = MetricsSender(url="http://spring:8080/api/metrics")
    sender_spring.send({"pc_id": "x", "timestamp": "t"}, [], {})
    assert captured["url"] == "http://spring:8080/api/metrics"
