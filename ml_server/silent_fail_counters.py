"""In-memory silent-fail counters for /status enrichment (F6 #18).

단일 프로세스 single-worker 가정. 모듈 전역 dict 에 누적.
멀티 프로세스/replica 환경에서는 외부 메트릭 시스템으로 교체 필요.
"""
from __future__ import annotations
import threading
from typing import Dict

_LOCK = threading.Lock()

_COUNTERS: Dict[str, int] = {
    "claude_mock_count":              0,
    "model_train_failure_count":      0,
    "model_predict_failure_count":    0,
    "retrieval_store_eviction_count": 0,
    "retrieval_evidence_skip_count":  0,
    "policy_reload_failed_count":     0,
}


def increment(key: str, delta: int = 1) -> None:
    if key not in _COUNTERS:
        return
    with _LOCK:
        _COUNTERS[key] += int(delta)


def get_silent_fail_counters() -> Dict[str, int]:
    """현재 카운터의 snapshot 을 dict 로 반환 (외부에서 mutate 불가)."""
    with _LOCK:
        return dict(_COUNTERS)


def reset_for_tests() -> None:
    with _LOCK:
        for k in _COUNTERS:
            _COUNTERS[k] = 0
