"""AgentRuntime.step() 의 실패 큐 자동 drain 통합 테스트.

검증 시나리오:
- 큐 5건 + 정상 mock → step() 1회로 5건 모두 송신, 큐 0
- 큐 5건 + 첫 응답 500 → 1건만 시도 후 break, 큐 5 유지
- 큐 10건 + 정상 → step() 1회 후 큐 잔여 5건 (RETRY_PER_CYCLE 비율 제한)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_core.runtime.loop import AgentRuntime, RETRY_PER_CYCLE
from agent_core.sender import LocalQueue, MetricsSender


def _build_runtime(monkeypatch, queue: LocalQueue, replay_results):
    """수집/탐지/sender.send 는 모두 stub 처리한 runtime 인스턴스 생성.

    replay_results: replay() 가 반환할 값들의 리스트 (순차 소비).
    """
    # AgentRuntime.__init__ 안에서 collector 가 실제 psutil 호출을 시도하므로,
    # collector / detectors / sender 모두를 단순 객체로 대체한다.
    rt = AgentRuntime.__new__(AgentRuntime)

    cfg = MagicMock()
    rt.config = cfg

    rt.collector = MagicMock()
    rt.local_window = MagicMock()
    rt.local_window.append = MagicMock()
    rt.hw_baseline = MagicMock()
    rt.hw_baseline.append = MagicMock()

    rt.threshold_det = MagicMock()
    rt.threshold_det.detect.return_value = []
    rt.absolute_det = MagicMock()
    rt.absolute_det.detect.return_value = []
    rt.hw_det = MagicMock()
    rt.hw_det.detect.return_value = []
    rt.boxplot_det = MagicMock()
    rt.boxplot_det.compute.return_value = {"available": False}

    # collect_and_update_windows 도 collector 호출 우회용으로 stub
    rt.collect_and_update_windows = lambda: {
        "pc_id": "test",
        "timestamp": "t",
        "cpu_percent": 0,
        "memory_percent": 0,
        "memory_used_gb": 0,
        "memory_total_gb": 0,
        "gpu": None,
        "outbound_mb": 0,
        "inbound_mb": 0,
        "external_packet_count": 0,
        "disk_read_mb": 0,
        "disk_write_mb": 0,
        "top_processes": [],
    }

    sender = MagicMock(spec=MetricsSender)
    # send() 는 정상 응답 반환 (drain 동작 자체에는 영향 없음)
    sender.send.return_value = {"verdict": "NORMAL"}
    sender.replay = MagicMock(side_effect=list(replay_results))

    rt.sender = sender
    rt.queue = queue

    # _print 출력 억제
    rt._print = lambda *a, **k: None

    return rt, sender


def _make_payload(i: int) -> dict:
    return {"pc_id": "p", "timestamp": f"t{i}", "seq": i}


def test_drain_5_items_all_success(monkeypatch, tmp_path):
    """큐 5건 + 정상 mock 서버 → step() 1회로 5건 송신, 큐 길이 0."""
    queue = LocalQueue(max_size=20, queue_path=tmp_path / "q.jsonl")
    for i in range(5):
        queue.put(_make_payload(i))
    assert len(queue) == 5

    rt, sender = _build_runtime(monkeypatch, queue, [True] * 5)
    rt.step()

    assert sender.replay.call_count == 5
    assert len(queue) == 0


def test_drain_breaks_on_first_failure(monkeypatch, tmp_path):
    """큐 5건 + 첫 응답 500 → 1건만 시도하고 break, 큐 길이 5 유지."""
    queue = LocalQueue(max_size=20, queue_path=tmp_path / "q.jsonl")
    for i in range(5):
        queue.put(_make_payload(i))

    rt, sender = _build_runtime(monkeypatch, queue, [False])
    rt.step()

    assert sender.replay.call_count == 1
    # 실패한 항목은 큐로 복귀해야 한다 → 길이 5 유지
    assert len(queue) == 5


def test_drain_rate_limited_to_retry_per_cycle(monkeypatch, tmp_path):
    """큐 10건 + 정상 → step() 1회 후 큐 잔여 5건 (RETRY_PER_CYCLE 비율 제한)."""
    assert RETRY_PER_CYCLE == 5
    queue = LocalQueue(max_size=20, queue_path=tmp_path / "q.jsonl")
    for i in range(10):
        queue.put(_make_payload(i))

    rt, sender = _build_runtime(monkeypatch, queue, [True] * 10)
    rt.step()

    assert sender.replay.call_count == RETRY_PER_CYCLE
    assert len(queue) == 10 - RETRY_PER_CYCLE
