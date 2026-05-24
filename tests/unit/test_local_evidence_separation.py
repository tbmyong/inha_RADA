"""P1-1 — LOCAL_* alerts split into separate local_evidence block.

docs/fp_field_analysis_v0.6.md §7-P1-1.

Before P1-1, agent-side LOCAL_* alerts (LOCAL_MEM_HIGH /
LOCAL_HW_CPU_DEGRADATION etc.) were appended to ``alerts[]`` so any
downstream consumer counting alerts treated them as engine evidence.
They polluted noise counts and audit views without ever changing the
verdict (which P0-2 already locked to engine output).

P1-1 moves LOCAL_* into a top-level ``local_evidence`` list — same
schema as alerts but reserved for client-side advisories. Verdict /
overall_severity / evidence_meta.active_signal_count remain untouched.
"""
from __future__ import annotations

from collections import deque

import pytest

from ml_server.model.requests import MetricsRequest
from ml_server.scorer.verdict_classifier import analyze_pattern, build_local_evidence


def _make_metrics(local_alerts=None,
                  cpu_pct: float = 5.0,
                  mem_pct: float = 30.0) -> MetricsRequest:
    return MetricsRequest(
        pc_id="pc-p1-1",
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


def test_high_local_alert_does_not_appear_in_alerts_list():
    """LOCAL_* with severity=HIGH must not appear in alerts[]."""
    m = _make_metrics(local_alerts=[{
        "type": "MEM_HIGH",
        "severity": "HIGH",
        "detail": "메모리 95%",
    }])
    result = analyze_pattern(m, deque(), slot="free")
    # NORMAL verdict, no engine alerts, no LOCAL_* leakage into alerts[].
    for alert in result["alerts"]:
        assert not alert["type"].startswith("LOCAL_"), \
            f"LOCAL_* leaked into alerts[]: {alert}"


def test_high_local_alert_appears_in_local_evidence():
    """The same alert is exposed in the top-level local_evidence list."""
    m = _make_metrics(local_alerts=[{
        "type": "MEM_HIGH",
        "severity": "HIGH",
        "detail": "메모리 95%",
    }])
    result = analyze_pattern(m, deque(), slot="free")
    le = result["local_evidence"]
    assert len(le) == 1
    assert le[0]["type"] == "LOCAL_MEM_HIGH"
    assert le[0]["severity"] == "HIGH"
    assert le[0]["score"] == 0
    assert "[에이전트]" in le[0]["detail"]


def test_medium_local_alert_split_too():
    """severity=MEDIUM also goes to local_evidence, not alerts[]."""
    m = _make_metrics(local_alerts=[{
        "type": "HW_CPU_DEGRADATION",
        "severity": "MEDIUM",
        "detail": "CPU baseline drift",
    }])
    result = analyze_pattern(m, deque(), slot="free")
    types = [a["type"] for a in result["alerts"]]
    assert not any(t.startswith("LOCAL_") for t in types)
    assert any(e["type"] == "LOCAL_HW_CPU_DEGRADATION"
               for e in result["local_evidence"])


def test_low_local_alert_dropped_entirely():
    """severity=LOW is dropped from both alerts[] and local_evidence
    (same as previous behavior — LOW was never persisted)."""
    m = _make_metrics(local_alerts=[{
        "type": "MEM_HIGH",
        "severity": "LOW",
        "detail": "weak signal",
    }])
    result = analyze_pattern(m, deque(), slot="free")
    assert result["local_evidence"] == []
    assert not any(a["type"].startswith("LOCAL_") for a in result["alerts"])


def test_local_evidence_excluded_from_active_signal_count():
    """active_signal_count counts signals dict only, not LOCAL_* alerts."""
    m = _make_metrics(local_alerts=[
        {"type": "MEM_HIGH", "severity": "HIGH", "detail": "x"},
        {"type": "HW_CPU_DEGRADATION", "severity": "MEDIUM", "detail": "y"},
    ])
    result = analyze_pattern(m, deque(), slot="free")
    meta = result["evidence_meta"]
    # No real engine signals → active_signal_count == 0 even though we
    # supplied two LOCAL_* alerts.
    assert meta["active_signal_count"] == 0
    # And no LOCAL_* names in active_signals list.
    assert not any(s.startswith("LOCAL_") for s in meta["active_signals"])


def test_no_local_alerts_yields_empty_local_evidence():
    m = _make_metrics(local_alerts=[])
    result = analyze_pattern(m, deque(), slot="free")
    assert result["local_evidence"] == []


def test_build_local_evidence_filters_severities():
    """build_local_evidence helper filters by severity directly."""
    m = _make_metrics(local_alerts=[
        {"type": "A", "severity": "HIGH", "detail": "h"},
        {"type": "B", "severity": "MEDIUM", "detail": "m"},
        {"type": "C", "severity": "LOW", "detail": "l"},
        {"type": "D", "severity": None, "detail": "n"},
    ])
    le = build_local_evidence(m)
    types = [e["type"] for e in le]
    assert types == ["LOCAL_A", "LOCAL_B"]
