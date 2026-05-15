"""ML 서버 다운 → put → 복구 → drain 시나리오.

flaky_ml_server fixture 로 첫 N회 ConnectionError 후 정상응답을 시뮬레이션.
"""
from __future__ import annotations

from client_core.sender import LocalQueue, MetricsSender


def test_local_queue_resend(synthetic_metrics_factory, unique_pc_id,
                            flaky_ml_server, tmp_path):
    """ML 다운 시 큐 적재 → 복구 후 drain → 정상 전송."""
    queue_path = tmp_path / "resend_queue.jsonl"
    queue = LocalQueue(max_size=50, queue_path=queue_path)
    sender = MetricsSender(url="http://localhost:8000/analyze", queue=queue)

    # 첫 2회는 ConnectionError, 3회째부터 정상
    flaky_ml_server(fail_first=2)

    m1 = synthetic_metrics_factory(unique_pc_id, cpu=20.0, mem=35.0)
    m2 = synthetic_metrics_factory(unique_pc_id, cpu=22.0, mem=36.0)

    # Step 1: ML 다운 — send 결과 None, 큐에 적재
    r1 = sender.send(m1, [], {})
    r2 = sender.send(m2, [], {})
    assert r1 is None and r2 is None
    assert len(queue) == 2, f"다운 시 큐 적재 실패: len={len(queue)}"

    # Step 2: ML 복구 — drain 후 큐의 페이로드 재전송
    pending = queue.drain()
    assert len(pending) == 2
    assert len(queue) == 0

    successes = []
    for payload in pending:
        # MetricsSender.send 시그니처는 (metrics, local_alerts, boxplot_signal)
        # 큐에는 이미 sanitize 된 통합 payload 가 들어있으므로 그대로 재전송.
        local_alerts = payload.pop("local_alerts", [])
        boxplot = payload.pop("boxplot_signal", {})
        result = sender.send(payload, local_alerts, boxplot)
        assert result is not None, "복구 후 재전송 실패"
        successes.append(result)

    assert len(successes) == 2
    assert all(r["pc_id"] == unique_pc_id for r in successes)
    # 큐는 비어있어야 함 (재전송 모두 성공)
    assert len(queue) == 0


def test_local_queue_persists_after_disconnect(synthetic_metrics_factory,
                                               unique_pc_id, monkeypatch,
                                               tmp_path):
    """ML 다운 → put → 인스턴스 폐기 → 재시작 시 디스크에서 복구."""
    import requests

    def always_fail(url, json=None, timeout=None, **kwargs):
        raise requests.exceptions.ConnectionError("permanent down")

    monkeypatch.setattr(requests, "post", always_fail)

    queue_path = tmp_path / "persist_queue.jsonl"
    q1 = LocalQueue(max_size=10, queue_path=queue_path)
    sender = MetricsSender(url="http://localhost:8000/analyze", queue=q1)

    for i in range(3):
        sender.send(synthetic_metrics_factory(unique_pc_id, cpu=20.0 + i),
                    [], {})

    assert len(q1) == 3
    del q1, sender

    # 새 인스턴스로 디스크에서 복구
    q2 = LocalQueue(max_size=10, queue_path=queue_path)
    assert len(q2) == 3
    items = q2.drain()
    assert all(item["pc_id"] == unique_pc_id for item in items)
