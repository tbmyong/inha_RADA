"""컨텍스트 감점 — startup -1, security_scan -2, maintenance_update -2,
lab_agent -1, class_or_free -1, max -4 clamp.
"""
from collections import deque

from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest


def _metrics(**overrides):
    base = dict(
        pc_id="pc-ctx", timestamp="2026-05-04T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )
    base.update(overrides)
    return MetricsRequest(**base)


def test_class_default_discount_minus_one():
    result = analyze_pattern(_metrics(), deque(), slot="class")
    assert result["scores"]["score_breakdown"]["context_discount"] == -1


def test_security_scan_discount_minus_two():
    m = _metrics(local_alerts=[{"type": "SECURITY_SCAN", "severity": "LOW", "detail": "scan"}])
    result = analyze_pattern(m, deque(), slot="class")
    assert result["scores"]["score_breakdown"]["context_discount"] == -2


def test_max_discount_clamped_at_minus_four():
    m = _metrics(local_alerts=[
        {"type": "STARTUP", "severity": "LOW", "detail": ""},
        {"type": "SECURITY_SCAN", "severity": "LOW", "detail": ""},
        {"type": "MAINTENANCE_UPDATE", "severity": "LOW", "detail": ""},
        {"type": "LAB_AGENT", "severity": "LOW", "detail": ""},
    ])
    result = analyze_pattern(m, deque(), slot="free")
    # -1 + -2 + -2 + -1 = -6 → clamp to -4
    assert result["scores"]["score_breakdown"]["context_discount"] == -4
