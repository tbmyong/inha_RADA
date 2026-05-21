"""Orchestrator 통합 — 22키 + derived_features (13키) 동시 출력 검증.

ML 페이로드 22키는 절대 깨지지 않으며, derived_features 는 선택 추가된다.
"""
from __future__ import annotations

from client_core.collector.orchestrator import CollectorOrchestrator


_DERIVED_KEYS = {
    "logical_cpu_count",
    "physical_cpu_count",
    "uptime_sec",
    "collector_version",
    "collection_interval_sec",
    "top_process_cpu_sum_normalized",
    "top_process_cpu_max_normalized",
    "external_connection_count_raw",
    "external_connection_count_truncated",
    "unique_remote_ip_count",
    "unique_remote_port_count",
    "unique_remote_process_count",
    "duplicate_connection_count",
    "gpu_metrics_missing_reason",
    # F5 — collector 미수신 사유 (수집 실패 vs 실제 0 분리)
    "network_collection_missing_reason",
    "process_collection_missing_reason",
    # Cryptojacking 탐지 system pattern (S1) — Windows GetLastInputInfo
    "user_idle_ms",
    "user_idle_collection_missing_reason",
}

# 22키 중 sender가 채우는 2개(local_alerts, boxplot_signal) 제외 → 20키
_CORE_20 = [
    "pc_id", "timestamp", "cpu_percent", "cpu_core_count",
    "memory_percent", "memory_used_gb", "memory_total_gb",
    "disk_read_mb", "disk_write_mb", "inbound_mb", "outbound_mb",
    "inbound_total_mb", "outbound_total_mb", "external_packet_count",
    "external_connection_count", "external_connections", "active_ports",
    "gpu", "top_processes", "loop_elapsed",
]


def _build_fast_orchestrator():
    from client_core.collector.cpu_mem import CpuMemCollector
    return CollectorOrchestrator(cpu_mem=CpuMemCollector(cpu_interval=0.0))


def test_22_core_keys_preserved():
    orch = _build_fast_orchestrator()
    metrics = orch.collect()
    for k in _CORE_20:
        assert k in metrics, f"missing core key: {k}"


def test_derived_features_present_with_18_keys():
    orch = _build_fast_orchestrator()
    metrics = orch.collect()
    assert "derived_features" in metrics
    df = metrics["derived_features"]
    assert isinstance(df, dict)
    # 16 (F5 까지) + user_idle_ms + user_idle_collection_missing_reason = 18
    assert len(df) == 18
    assert set(df.keys()) == _DERIVED_KEYS


def test_derived_features_value_types_sane():
    orch = _build_fast_orchestrator()
    metrics = orch.collect()
    df = metrics["derived_features"]
    assert isinstance(df["logical_cpu_count"], int)
    assert isinstance(df["physical_cpu_count"], int)
    assert isinstance(df["uptime_sec"], int) and df["uptime_sec"] >= 0
    assert isinstance(df["collector_version"], str)
    assert df["collection_interval_sec"] == 5
    assert isinstance(df["external_connection_count_truncated"], bool)
    assert df["gpu_metrics_missing_reason"] is None or isinstance(
        df["gpu_metrics_missing_reason"], str
    )


def test_derived_features_isolation_when_orchestrator_collect_succeeds():
    """22키가 채워졌으면 derived_features 실패가 22키에 영향 없어야 한다.

    여기서는 derived 조립 자체는 성공해야 하나, 안전장치가 try/except 로
    감싸져 있다는 점만 구조적으로 확인 (오케스트레이터 collect가 예외 던지지 않음).
    """
    orch = _build_fast_orchestrator()
    # 반복 호출에도 안정적이어야 함
    for _ in range(2):
        m = orch.collect()
        assert "pc_id" in m
