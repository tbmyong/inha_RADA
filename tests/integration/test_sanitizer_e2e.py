"""numpy 타입 페이로드 회귀 — sanitize → json.dumps → ML 서버 200."""
from __future__ import annotations

import json

from agent_core.sender import MetricsSender, sanitize_for_json


def test_sanitizer_e2e(numpy_polluted_metrics, ml_request_shim):
    """numpy 오염 dict → sanitize → json 직렬화 가능 → TestClient 200."""
    metrics = numpy_polluted_metrics

    # 1) sanitize 전에는 일부 numpy 타입이 json.dumps 실패할 수 있음
    sanitized = sanitize_for_json(dict(metrics))

    # 2) 표준 json 직렬화 성공
    encoded = json.dumps(sanitized)
    assert isinstance(encoded, str) and len(encoded) > 0

    # 3) Python 기본 타입으로 변환되었는지
    assert isinstance(sanitized["cpu_percent"], float)
    assert isinstance(sanitized["external_packet_count"], int)
    assert isinstance(sanitized["active_ports"], list)
    assert all(isinstance(p, int) for p in sanitized["active_ports"])

    # 4) MetricsSender (sanitize 내장) → ML 서버 e2e
    sender = MetricsSender(url="http://localhost:8000/analyze")
    result = sender.send(metrics, local_alerts=[], boxplot_signal={})

    assert result is not None
    assert result["pc_id"] == metrics["pc_id"]
    assert result["overall_severity"] in {"NORMAL", "MEDIUM", "HIGH", "CRITICAL"}


def test_sanitizer_handles_nested_numpy():
    """중첩 dict / list 안의 numpy 타입도 모두 변환."""
    import numpy as np

    payload = {
        "outer_bool": np.bool_(True),
        "list": [np.int64(1), np.float64(2.5), {"inner": np.bool_(False)}],
        "dict": {"arr": np.array([1.0, 2.0]), "tuple": (np.int32(7),)},
    }
    sanitized = sanitize_for_json(payload)
    encoded = json.dumps(sanitized)

    decoded = json.loads(encoded)
    assert decoded["outer_bool"] is True
    assert decoded["list"][0] == 1
    assert decoded["list"][1] == 2.5
    assert decoded["list"][2]["inner"] is False
    assert decoded["dict"]["arr"] == [1.0, 2.0]
    assert decoded["dict"]["tuple"] == [7]
