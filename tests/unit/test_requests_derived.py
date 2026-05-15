"""MetricsRequest.derived_features — Optional 필드 수신 보장.

2단계: 본 필드는 점수 계산에 사용되지 않으며, 수신/보존만 검증한다.
기존 22키 순서/이름은 절대 변경되지 않아야 한다 (test_metrics_request_schema 참조).
"""
from __future__ import annotations

from ml_server.model.requests import MetricsRequest


def _base_payload() -> dict:
    return {
        "pc_id":                     "pc-derived-1",
        "timestamp":                 "2026-05-13T10:00:00",
        "cpu_percent":               12.0,
        "cpu_core_count":            8,
        "memory_percent":            30.0,
        "memory_used_gb":            3.0,
        "memory_total_gb":           16.0,
        "disk_read_mb":              0.1,
        "disk_write_mb":             0.2,
        "inbound_mb":                0.0,
        "outbound_mb":               0.0,
        "inbound_total_mb":          0.0,
        "outbound_total_mb":         0.0,
        "external_packet_count":     0,
        "external_connection_count": 0,
        "external_connections":      [],
        "active_ports":              [],
        "gpu":                       None,
        "top_processes":             [],
        "loop_elapsed":              0.01,
        "local_alerts":              [],
        "boxplot_signal":            {},
    }


def test_derived_features_preserved_when_present():
    """case A — payload에 derived_features 포함 시 그대로 보존."""
    payload = _base_payload()
    payload["derived_features"] = {
        "cpu_mem_ratio":  0.4,
        "io_pressure":    1.23,
        "tags":           ["spike", "io"],
    }

    m = MetricsRequest(**payload)
    assert m.derived_features is not None
    assert m.derived_features["cpu_mem_ratio"] == 0.4
    assert m.derived_features["io_pressure"] == 1.23
    assert m.derived_features["tags"] == ["spike", "io"]


def test_derived_features_default_none_when_missing():
    """case B — derived_features 누락 시 None (하위 호환)."""
    payload = _base_payload()
    assert "derived_features" not in payload

    m = MetricsRequest(**payload)
    assert m.derived_features is None
