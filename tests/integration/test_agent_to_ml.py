"""agent_core orchestrator → MetricsSender → ML 서버 e2e.

requests.post 를 TestClient 로 라우팅하는 ml_request_shim 사용 →
실제 HTTP 없이 ML 서버 /analyze 분석 파이프라인 전체를 검증.
"""
from __future__ import annotations

import json

import pytest
import requests

from agent_core.model import MetricsPayload
from agent_core.sender import LocalQueue, MetricsSender
from ml_server.model.requests import MetricsRequest


@pytest.fixture
def springboot_202_empty(monkeypatch):
    """Spring Boot 202 Accepted + 빈 body 시뮬.

    MetricsSender mode=springboot 경로 e2e: requests.post → 202 응답.
    resp.json() 은 ValueError 를 던져 빈 body 경로를 강제한다.
    """
    class _Resp:
        status_code = 202

        def json(self):
            raise json.JSONDecodeError("empty body", "", 0)

    calls = {"count": 0, "last_headers": None}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        calls["count"] += 1
        calls["last_headers"] = headers
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    return calls


def test_agent_to_ml_e2e(synthetic_metrics_factory, unique_pc_id, ml_request_shim):
    """22키 metrics dict → MetricsSender.send → ML 서버 200 + 정상 verdict."""
    metrics = synthetic_metrics_factory(unique_pc_id, cpu=25.0, mem=40.0)
    sender = MetricsSender(url="http://localhost:8000/analyze")

    result = sender.send(metrics, local_alerts=[], boxplot_signal={})

    assert result is not None, "ML 서버 응답이 None — shim 라우팅 실패"
    # B 팀원이 동기화한 응답 키 트리 검증
    assert result["pc_id"] == unique_pc_id
    assert "overall_severity" in result
    assert "verdict" in result
    assert result["overall_severity"] in {"NORMAL", "MEDIUM", "HIGH", "CRITICAL"}
    assert result["verdict"] in {"NORMAL", "OBSERVE", "SUSPICIOUS",
                                 "HIGH_RISK"}
    assert "isolation_forest" in result
    assert "scores" in result
    assert "signals" in result
    # NORMAL 인 경우 agent 필드는 None
    if result["verdict"] == "NORMAL":
        assert result["agent"] is None


def test_22key_round_trip(synthetic_metrics_factory, unique_pc_id):
    """MetricsPayload.validate() + Pydantic MetricsRequest 역직렬화 round-trip."""
    metrics = synthetic_metrics_factory(unique_pc_id)
    metrics["local_alerts"] = []
    metrics["boxplot_signal"] = {}

    # 1) 22 키 검증 (필수 키 누락 없음)
    missing = MetricsPayload.validate(metrics)
    assert missing == [], f"22키 페이로드에 누락 키: {missing}"

    # 2) Pydantic 모델 역직렬화 성공
    req = MetricsRequest(**metrics)
    assert req.pc_id == unique_pc_id
    assert req.cpu_percent == metrics["cpu_percent"]
    assert req.external_packet_count == 3

    # 3) 모델 → dict round-trip 시 키 보존
    restored = req.model_dump()
    for key in ("pc_id", "timestamp", "cpu_percent", "memory_percent",
                "inbound_mb", "outbound_mb", "external_packet_count"):
        assert key in restored


def test_springboot_202_empty_body_e2e(synthetic_metrics_factory, unique_pc_id,
                                       springboot_202_empty, tmp_path):
    """Spring Boot 202 + 빈 body → result == {} + 큐 미적재."""
    metrics = synthetic_metrics_factory(unique_pc_id, cpu=25.0, mem=40.0)
    queue = LocalQueue(max_size=10, queue_path=tmp_path / "q.jsonl")
    sender = MetricsSender(
        url="http://sb:8080/api/metrics",
        queue=queue,
        mode="springboot",
        api_key="K",
    )

    result = sender.send(metrics, local_alerts=[], boxplot_signal={})

    assert result == {}
    assert len(queue) == 0
    assert springboot_202_empty["count"] == 1
    # X-API-Key 헤더 전송 확인
    assert springboot_202_empty["last_headers"].get("X-API-Key") == "K"
