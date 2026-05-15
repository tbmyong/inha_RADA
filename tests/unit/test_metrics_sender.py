"""agent_core.sender.metrics_sender 단위 테스트.

mode 별 응답코드 분기:
- 200 (mlserver 정상)  → JSON body 반환, 큐 미적재
- 202 (springboot 정상, 빈 body 가능) → {} 반환, 큐 미적재
- 4xx / 5xx           → None 반환, 큐 적재
- ConnectionError     → None 반환, 큐 적재
"""
from __future__ import annotations

import json

import pytest
import requests

from agent_core.sender import LocalQueue, MetricsSender


class _Resp:
    def __init__(self, status_code: int, body=None, raise_json: bool = False):
        self.status_code = status_code
        self._body = body
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json body")
        return self._body


@pytest.fixture
def queue(tmp_path):
    return LocalQueue(max_size=10, queue_path=tmp_path / "q.jsonl")


def _patch_post(monkeypatch, resp):
    calls = {"count": 0, "last": None}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        calls["count"] += 1
        calls["last"] = {"url": url, "json": json, "headers": headers}
        return resp

    monkeypatch.setattr(requests, "post", fake_post)
    return calls


def test_status_200_returns_json_no_queue(monkeypatch, queue):
    resp = _Resp(200, body={"verdict": "ok"})
    _patch_post(monkeypatch, resp)
    sender = MetricsSender(url="http://ml:8000/analyze", queue=queue, mode="mlserver")

    result = sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    assert result == {"verdict": "ok"}
    assert len(queue) == 0


def test_status_202_empty_body_returns_dict_no_queue(monkeypatch, queue):
    # Spring Boot 202 는 빈 body. resp.json() 이 ValueError 를 던질 수 있다.
    resp = _Resp(202, raise_json=True)
    _patch_post(monkeypatch, resp)
    sender = MetricsSender(
        url="http://sb:8080/api/metrics",
        queue=queue,
        mode="springboot",
        api_key="K",
    )

    result = sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    assert result == {}
    assert len(queue) == 0


def test_status_202_with_jsondecodeerror_guard(monkeypatch, queue):
    # json.JSONDecodeError 는 ValueError 의 하위 클래스지만, 명시적으로 케이스 분리 검증.
    class _DecRespError:
        status_code = 202

        def json(self):
            raise json.JSONDecodeError("bad", "doc", 0)

    _patch_post(monkeypatch, _DecRespError())
    sender = MetricsSender(
        url="http://sb:8080/api/metrics",
        queue=queue,
        mode="springboot",
        api_key="K",
    )

    result = sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    assert result == {}
    assert len(queue) == 0


def test_status_400_returns_none_and_queues(monkeypatch, queue):
    resp = _Resp(400, raise_json=True)
    _patch_post(monkeypatch, resp)
    sender = MetricsSender(url="http://ml:8000/analyze", queue=queue, mode="mlserver")

    result = sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    assert result is None
    assert len(queue) == 1


def test_status_500_returns_none_and_queues(monkeypatch, queue):
    resp = _Resp(500, raise_json=True)
    _patch_post(monkeypatch, resp)
    sender = MetricsSender(
        url="http://sb:8080/api/metrics",
        queue=queue,
        mode="springboot",
        api_key="K",
    )

    result = sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    assert result is None
    assert len(queue) == 1


def test_connection_error_queues(monkeypatch, queue):
    def boom(url, json=None, headers=None, timeout=None, **kwargs):
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(requests, "post", boom)
    sender = MetricsSender(url="http://ml:8000/analyze", queue=queue, mode="mlserver")

    result = sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    assert result is None
    assert len(queue) == 1


def test_status_202_with_json_body_returns_dict(monkeypatch, queue):
    """Spring Boot 202 + JSON body → dict 반환, 큐 미적재."""
    resp = _Resp(202, body={"accepted": True, "ref": "abc"})
    _patch_post(monkeypatch, resp)
    sender = MetricsSender(
        url="http://sb:8080/api/metrics",
        queue=queue,
        mode="springboot",
        api_key="K",
    )

    result = sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    assert result == {"accepted": True, "ref": "abc"}
    assert len(queue) == 0


def test_springboot_mode_includes_api_key_header(monkeypatch, queue):
    """mode=springboot → X-API-Key 헤더 포함."""
    resp = _Resp(202, raise_json=True)
    calls = _patch_post(monkeypatch, resp)
    sender = MetricsSender(
        url="http://sb:8080/api/metrics",
        queue=queue,
        mode="springboot",
        api_key="SECRET-K",
    )

    sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    headers = calls["last"]["headers"]
    assert headers is not None
    assert headers.get("X-API-Key") == "SECRET-K"
    assert headers.get("Content-Type") == "application/json"


def test_mlserver_mode_has_no_headers(monkeypatch, queue):
    """mode=mlserver → 헤더 없음 (requests.post 에 headers 미전달)."""
    resp = _Resp(200, body={"ok": True})
    calls = _patch_post(monkeypatch, resp)
    sender = MetricsSender(url="http://ml:8000/analyze", queue=queue, mode="mlserver")

    sender.send({"pc_id": "pc1", "timestamp": "t"}, [], {})
    # mlserver 경로는 headers kwarg 없이 post 호출 → fake_post 의 headers=None
    assert calls["last"]["headers"] is None
