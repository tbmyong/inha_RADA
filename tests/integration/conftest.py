"""통합 테스트 픽스처.

- client: FastAPI TestClient
- reset_stores: pc_history_store / model_store / score_history_store 초기화 (autouse)
- unset_anthropic_key: ANTHROPIC_API_KEY env 제거 (autouse)

팀원 C 추가 (2026-05-07):
- unique_pc_id: pc_history_store 전역 상태와 충돌하지 않도록 매 테스트마다 새 pc_id
- synthetic_metrics_factory: orchestrator collect()가 반환하는 22키 dict 결정론적 합성
- numpy_polluted_metrics: numpy 타입(float64/bool_/ndarray)이 섞인 페이로드
- ml_request_shim: requests.post → FastAPI TestClient 라우팅 (MetricsSender e2e 용)
- flaky_ml_server: 첫 N회 ConnectionError 후 정상응답
"""
from __future__ import annotations

import datetime
import uuid
from typing import Callable, Dict
from urllib.parse import urlparse

import numpy as np
import pytest
import requests
from fastapi.testclient import TestClient

from ml_server.main import app
from ml_server.storage import pc_history_store, model_store, score_history_store


@pytest.fixture(autouse=True)
def unset_anthropic_key(monkeypatch):
    """ANTHROPIC_API_KEY 환경변수 미설정 보장."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


@pytest.fixture(autouse=True)
def reset_stores():
    """테스트 간 전역 저장소 격리."""
    pc_history_store.pc_history.clear()
    pc_history_store.pc_train_history.clear()
    pc_history_store.all_pc_latest.clear()
    model_store.pc_models.clear()
    score_history_store.pc_score_history.clear()
    score_history_store.rule_score_history.clear()
    yield
    pc_history_store.pc_history.clear()
    pc_history_store.pc_train_history.clear()
    pc_history_store.all_pc_latest.clear()
    model_store.pc_models.clear()
    score_history_store.pc_score_history.clear()
    score_history_store.rule_score_history.clear()


@pytest.fixture
def client():
    """FastAPI TestClient."""
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────── 팀원 C 추가 fixture

@pytest.fixture
def unique_pc_id() -> str:
    """매 테스트마다 unique pc_id (전역 store 격리 보강)."""
    return f"test-{uuid.uuid4().hex[:12]}"


def _build_synthetic_metrics(pc_id: str, *, cpu: float = 25.0, mem: float = 40.0,
                             timestamp: str | None = None) -> Dict:
    """orchestrator.collect() 형태의 22키 dict 결정론적 합성.

    psutil/GPU 의존성을 우회 - 어떤 환경에서도 동일 입력. 22키는
    agent_core.model.payload.MetricsPayload.keys() 와 일치.
    """
    return {
        "pc_id": pc_id,
        "timestamp": timestamp or datetime.datetime.now().isoformat(),
        "cpu_percent": float(cpu),
        "cpu_core_count": 8,
        "memory_percent": float(mem),
        "memory_used_gb": 4.0,
        "memory_total_gb": 16.0,
        "disk_read_mb": 0.5,
        "disk_write_mb": 0.7,
        "inbound_mb": 0.1,
        "outbound_mb": 0.2,
        "inbound_total_mb": 100.0,
        "outbound_total_mb": 200.0,
        "external_packet_count": 3,
        "external_connection_count": 3,
        "external_connections": [
            {"remote_ip": "8.8.8.8", "remote_port": 443, "process": "chrome.exe"},
        ],
        "active_ports": [443, 80, 8080],
        "gpu": None,
        "top_processes": [
            {"name": "python.exe", "cpu_percent": 1.2, "memory_percent": 0.5},
        ],
        "loop_elapsed": 0.012,
    }


@pytest.fixture
def synthetic_metrics_factory() -> Callable[..., Dict]:
    """결정론적 22키 dict factory."""
    return _build_synthetic_metrics


@pytest.fixture
def numpy_polluted_metrics(unique_pc_id: str) -> Dict:
    """numpy 타입이 섞인 페이로드 (sanitizer 회귀 테스트용)."""
    base = _build_synthetic_metrics(unique_pc_id)
    base["cpu_percent"] = np.float64(72.5)
    base["memory_percent"] = np.float64(80.0)
    base["external_packet_count"] = np.int64(3)
    base["active_ports"] = np.array([443, 80, 8080])
    base["loop_elapsed"] = np.float32(0.012)
    return base


@pytest.fixture
def ml_request_shim(monkeypatch, client):
    """requests.post 호출을 FastAPI TestClient.post 로 라우팅.

    MetricsSender 가 requests.post 를 직접 호출하므로 실제 네트워크 없이
    e2e 분석 파이프라인 검증 가능. client fixture(TestClient) 재사용.
    """
    def fake_post(url, json=None, timeout=None, **kwargs):
        path = urlparse(url).path or "/analyze"
        return client.post(path, json=json)

    monkeypatch.setattr(requests, "post", fake_post)
    return fake_post


@pytest.fixture
def flaky_ml_server(monkeypatch, client):
    """첫 N회 ConnectionError → 이후 정상응답.

    사용:
        configure = flaky_ml_server  # fixture 자체가 configure callable
        configure(fail_first=2)
        sender.send(...)  # 첫 2회 실패, 3회째부터 200
    """
    state: Dict[str, int] = {"calls": 0, "fail_first": 0}

    def fake_post(url, json=None, timeout=None, **kwargs):
        state["calls"] += 1
        if state["calls"] <= state["fail_first"]:
            raise requests.exceptions.ConnectionError("simulated ML down")
        path = urlparse(url).path or "/analyze"
        return client.post(path, json=json)

    monkeypatch.setattr(requests, "post", fake_post)

    def configure(fail_first: int = 1):
        state["fail_first"] = fail_first
        state["calls"] = 0
        return state

    configure.state = state  # 디버그/검증용
    return configure
