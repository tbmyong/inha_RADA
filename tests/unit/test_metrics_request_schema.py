"""MetricsRequest Pydantic 스키마 — 22키 정합 검증.

agent_core.model.payload.ML_PAYLOAD_KEYS (22) 와 일치하는 페이로드가 silent
drop 없이 모두 접근 가능해야 한다. external_connection_count / loop_elapsed
누락 버그 회귀 방지.
"""
from __future__ import annotations

import pytest

from ml_server.model.requests import MetricsRequest, GpuMetrics
from agent_core.model.payload import ML_PAYLOAD_KEYS


def _full_payload() -> dict:
    return {
        "pc_id":                 "pc-schema-1",
        "timestamp":             "2026-05-13T10:00:00",
        "cpu_percent":           25.0,
        "cpu_core_count":        8,
        "memory_percent":        40.0,
        "memory_used_gb":        4.0,
        "memory_total_gb":       16.0,
        "disk_read_mb":          0.5,
        "disk_write_mb":         0.7,
        "inbound_mb":            0.1,
        "outbound_mb":           0.2,
        "inbound_total_mb":      100.0,
        "outbound_total_mb":     200.0,
        "external_packet_count": 3,
        "external_connection_count": 5,
        "external_connections":  [
            {"remote_ip": "8.8.8.8", "remote_port": 443, "process": "chrome.exe"},
        ],
        "active_ports":          [80, 443, 8080],
        "gpu":                   None,
        "top_processes":         [
            {"name": "python.exe", "cpu_percent": 1.2, "memory_percent": 0.5},
        ],
        "loop_elapsed":          0.013,
        "local_alerts":          [],
        "boxplot_signal":        {},
    }


def test_full_22key_payload_no_silent_drop():
    """22 키 페이로드 → 모든 필드가 모델에 매핑되고 접근 가능."""
    payload = _full_payload()
    # 22 키 검증
    assert len(payload) == 22
    assert set(payload.keys()) == set(ML_PAYLOAD_KEYS), (
        f"keys mismatch: {set(payload.keys()) ^ set(ML_PAYLOAD_KEYS)}"
    )

    m = MetricsRequest(**payload)

    # 신규 2키 silent drop 회귀 — 반드시 접근 가능
    assert m.external_connection_count == 5
    assert m.loop_elapsed == pytest.approx(0.013)

    # 기존 키 sanity
    assert m.pc_id == "pc-schema-1"
    assert m.cpu_percent == pytest.approx(25.0)
    assert m.external_packet_count == 3
    assert m.inbound_total_mb == pytest.approx(100.0)
    assert m.outbound_total_mb == pytest.approx(200.0)
    assert m.active_ports == [80, 443, 8080]
    assert m.boxplot_signal == {}


def test_new_keys_default_when_missing():
    """누락 시 default (0 / 0.0) 적용. 기존 클라이언트 호환."""
    payload = _full_payload()
    payload.pop("external_connection_count")
    payload.pop("loop_elapsed")

    m = MetricsRequest(**payload)
    assert m.external_connection_count == 0
    assert m.loop_elapsed == 0.0


def test_model_fields_cover_all_22_keys():
    """Pydantic 모델이 22 키 전부를 필드로 보유."""
    # pydantic v2: model_fields, v1: __fields__
    fields = getattr(MetricsRequest, "model_fields", None) or MetricsRequest.__fields__
    field_names = set(fields.keys())
    missing = set(ML_PAYLOAD_KEYS) - field_names
    assert not missing, f"MetricsRequest missing fields: {missing}"


def test_pydantic_v2_dump_roundtrip():
    """Pydantic v2 호환 — model_dump() 라운드트립."""
    payload = _full_payload()
    m = MetricsRequest(**payload)
    # v2 호환 dump
    dump_fn = getattr(m, "model_dump", None) or m.dict
    d = dump_fn()
    assert d["external_connection_count"] == 5
    assert d["loop_elapsed"] == pytest.approx(0.013)
    # 재구성 가능
    m2 = MetricsRequest(**d)
    assert m2.external_connection_count == 5
    assert m2.loop_elapsed == pytest.approx(0.013)


def test_gpu_nested_model_still_works():
    """기존 GpuMetrics 중첩 모델 회귀 보호."""
    payload = _full_payload()
    payload["gpu"] = {
        "name":            "RTX 3060",
        "load_percent":    50.0,
        "memory_used_mb":  4000.0,
        "memory_total_mb": 8192.0,
        "memory_percent":  48.8,
    }
    m = MetricsRequest(**payload)
    assert isinstance(m.gpu, GpuMetrics)
    assert m.gpu.name == "RTX 3060"
