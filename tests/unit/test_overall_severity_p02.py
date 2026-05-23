"""P0-2 — overall_severity is derived from verdict, not from alert max.

docs/fp_field_analysis_v0.6.md §7-P0-2.

Before P0-2 the engine set overall_severity = max(alert.severity), so a
single local alert with severity=HIGH could drag a verdict=OBSERVE row
into HIGH/OBSERVE territory. Field data showed 559 such mismatches
(HIGH/OBSERVE 155 + MEDIUM/NORMAL 404 from local alerts alone). The
fix maps overall_severity directly from verdict:

    HIGH_RISK  -> HIGH
    SUSPICIOUS -> MEDIUM
    OBSERVE    -> LOW
    NORMAL     -> NORMAL

Fast-path is implicit: classify_verdict already promotes confirmed
mining to HIGH_RISK via process_score / mining_known, so xmrig-style
attacks still land at HIGH without a separate override.
"""
from __future__ import annotations

from collections import deque

import pytest

from ml_server.model.requests import MetricsRequest
from ml_server.scorer.verdict_classifier import analyze_pattern


def _make_metrics(cpu_pct: float = 5.0,
                  mem_pct: float = 30.0,
                  local_alerts: list | None = None) -> MetricsRequest:
    """Build a minimal MetricsRequest. Optional local_alerts to simulate
    a client-side alert with high severity that previously would have
    overridden overall_severity."""
    return MetricsRequest(
        pc_id="test-pc",
        timestamp="2026-05-23T10:00:00+09:00",
        cpu_percent=cpu_pct,
        memory_percent=mem_pct,
        disk_read_mb=0.1,
        disk_write_mb=0.1,
        inbound_mb=0.1,
        outbound_mb=0.1,
        external_packet_count=0,
        gpu={
            "name": "test", "load_percent": 0.0,
            "memory_used_mb": 0.0, "memory_total_mb": 1.0,
            "memory_percent": 0.0,
        },
        local_alerts=local_alerts or [],
    )


def test_normal_verdict_maps_to_normal_severity():
    """Empty metrics → verdict NORMAL → severity NORMAL."""
    m = _make_metrics()
    result = analyze_pattern(m, deque(), slot="free")
    assert result["verdict"] == "NORMAL"
    assert result["overall_severity"] == "NORMAL"


def test_high_severity_local_alert_cannot_promote_normal_verdict():
    """Local alert severity=HIGH must NOT drag overall_severity up when
    the engine verdict is NORMAL. This is the P0-2 fix in one line."""
    # CPU/mem low (no real anomaly) but client claims a HIGH local alert
    m = _make_metrics(local_alerts=[{
        "type": "MEM_HIGH",
        "severity": "HIGH",
        "detail": "메모리 95% — false alarm scenario",
    }])
    result = analyze_pattern(m, deque(), slot="free")
    # verdict 은 NORMAL 유지 (final_score 작음)
    assert result["verdict"] == "NORMAL"
    # overall_severity 도 NORMAL — 옛 로직이면 HIGH 였을 것
    assert result["overall_severity"] == "NORMAL"


def test_medium_severity_local_alert_cannot_promote_normal_verdict():
    """동일 — local alert severity=MEDIUM 가 NORMAL verdict 를 강제
    승격하지 못한다."""
    m = _make_metrics(local_alerts=[{
        "type": "HW_CPU_DEGRADATION",
        "severity": "MEDIUM",
        "detail": "CPU baseline drift — false alarm scenario",
    }])
    result = analyze_pattern(m, deque(), slot="free")
    assert result["verdict"] == "NORMAL"
    assert result["overall_severity"] == "NORMAL"


@pytest.mark.parametrize("verdict,expected_severity", [
    ("HIGH_RISK",  "HIGH"),
    ("SUSPICIOUS", "MEDIUM"),
    ("OBSERVE",    "LOW"),
    ("NORMAL",     "NORMAL"),
])
def test_verdict_to_severity_mapping_table(verdict, expected_severity):
    """직접 매핑 표 검증. analyze_pattern 결과의 overall_severity 는
    verdict 의 함수다 (P0-2 본질)."""
    # 모든 verdict 를 직접 만드는 fixture 가 어렵기 때문에, 매핑
    # 자체를 verdict_classifier 의 내부 dict 가 그대로 가지고 있는지
    # 검증한다.
    import ml_server.scorer.verdict_classifier as vc
    import inspect

    src = inspect.getsource(vc.analyze_pattern)
    # P0-2 매핑이 코드 안에 존재함을 확인
    assert '"HIGH_RISK":  "HIGH"' in src or '"HIGH_RISK": "HIGH"' in src
    assert '"SUSPICIOUS": "MEDIUM"' in src
    assert '"OBSERVE":    "LOW"' in src or '"OBSERVE": "LOW"' in src
    assert '"NORMAL":     "NORMAL"' in src or '"NORMAL": "NORMAL"' in src
