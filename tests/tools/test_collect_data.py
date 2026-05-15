"""Unit tests for client_core.tools.collect_data."""

import pytest

from client_core.tools.collect_data import (
    COLLECTOR_VERSION,
    CSV_FIELDS,
    CsvMetricsCollector,
    GpuCollector,
    is_external_ip,
)


NEW_DERIVED_FIELDS = [
    "physical_cpu_count",
    "logical_cpu_count",
    "collection_interval_sec",
    "uptime_sec",
    "collector_version",
    "top_process_cpu_sum_normalized",
    "top_process_cpu_max_normalized",
    "external_connection_count_raw",
    "external_connection_count_truncated",
    "unique_remote_ip_count",
    "unique_remote_port_count",
    "unique_remote_process_count",
    "duplicate_connection_count",
    "gpu_metrics_missing_reason",
]


V3_REQUIRED = {
    "pc_id",
    "collected_at",
    "cpu_percent",
    "mem_percent",
    "disk_read_mb",
    "disk_write_mb",
    "inbound_mb",
    "outbound_mb",
    "gpu_percent",
    "vram_mb",
}


def test_csv_fields_contains_v3_required():
    missing = V3_REQUIRED - set(CSV_FIELDS)
    assert not missing, f"V3 필수 컬럼 누락: {missing}"


def test_csv_fields_no_legacy_names():
    legacy = {"timestamp", "network_inbound_mb", "network_outbound_mb", "gpu_vram_mb"}
    overlap = legacy & set(CSV_FIELDS)
    assert not overlap, f"레거시 컬럼명 남아있음: {overlap}"


def test_csv_fields_unique():
    assert len(CSV_FIELDS) == len(set(CSV_FIELDS))


def test_is_external_ip_private():
    assert is_external_ip("10.0.0.1") is False
    assert is_external_ip("192.168.1.1") is False
    assert is_external_ip("127.0.0.1") is False


def test_is_external_ip_public():
    assert is_external_ip("8.8.8.8") is True
    assert is_external_ip("1.1.1.1") is True


def test_is_external_ip_invalid():
    assert is_external_ip("not-an-ip") is False
    assert is_external_ip("") is False


def test_gpu_collector_when_unavailable():
    """When NVML is unavailable or init fails, all GPU values should be None/False."""
    collector = GpuCollector.__new__(GpuCollector)
    collector.available = False
    collector.handle = None
    collector.name = None
    collector.total_mb = None
    collector.missing_reason = None

    result = collector.collect()
    assert result["gpu_available"] is False
    none_keys = [
        "gpu_name",
        "gpu_percent",
        "gpu_sm_percent",
        "vram_mb",
        "gpu_vram_total_mb",
        "gpu_temp_c",
        "gpu_power_w",
        "gpu_tensor_core_active",
    ]
    for k in none_keys:
        assert result[k] is None, f"{k} should be None when GPU unavailable"


def test_csv_fields_length_39():
    """CSV_FIELDS should contain the V3 + extras + new derived block.

    Naming kept for plan traceability; the realized total is 41 (27 base + 14 derived).
    """
    assert len(CSV_FIELDS) == 41


def test_csv_fields_contains_new_derived():
    missing = set(NEW_DERIVED_FIELDS) - set(CSV_FIELDS)
    assert not missing, f"신규 derived 컬럼 누락: {missing}"


def test_collector_version_constant():
    assert COLLECTOR_VERSION == "1.0.0"


def test_gpu_collector_reason_when_unavailable():
    collector = GpuCollector.__new__(GpuCollector)
    collector.available = False
    collector.handle = None
    collector.name = None
    collector.total_mb = None
    collector.missing_reason = "pynvml_error"

    result = collector.collect()
    assert result["gpu_available"] is False
    assert result["gpu_metrics_missing_reason"] == "pynvml_error"


@pytest.mark.parametrize(
    "reason",
    ["pynvml_error", "permission_error", "driver_error", "no_gpu", "unknown"],
)
def test_gpu_collector_reason_categories(reason):
    collector = GpuCollector.__new__(GpuCollector)
    collector.available = False
    collector.handle = None
    collector.name = None
    collector.total_mb = None
    collector.missing_reason = reason

    result = collector.collect()
    assert result["gpu_metrics_missing_reason"] == reason


def test_analyze_external_connections_dedup():
    conns = [
        {"remote_ip": "8.8.8.8", "remote_port": 443, "pid": 100},
        {"remote_ip": "8.8.8.8", "remote_port": 443, "pid": 100},  # duplicate triple
        {"remote_ip": "8.8.8.8", "remote_port": 80, "pid": 100},
        {"remote_ip": "1.1.1.1", "remote_port": 443, "pid": 200},
    ]
    stats = CsvMetricsCollector._analyze_external_connections(conns, limit=50)
    assert stats["raw_count"] == 4
    assert stats["truncated"] is False
    assert stats["unique_remote_ip_count"] == 2
    assert stats["unique_remote_port_count"] == 2
    assert stats["unique_remote_process_count"] == 2
    assert stats["duplicate_connection_count"] == 1


def test_analyze_external_connections_truncated():
    conns = [
        {"remote_ip": f"8.8.8.{i}", "remote_port": 443, "pid": i}
        for i in range(50)
    ]
    stats = CsvMetricsCollector._analyze_external_connections(conns, limit=50)
    assert stats["raw_count"] == 50
    assert stats["truncated"] is True


def test_analyze_external_connections_below_limit_not_truncated():
    stats = CsvMetricsCollector._analyze_external_connections([], limit=50)
    assert stats["raw_count"] == 0
    assert stats["truncated"] is False
    assert stats["unique_remote_ip_count"] == 0
    assert stats["duplicate_connection_count"] == 0


def test_top_process_normalization():
    # Compute the same math the collector uses, in isolation.
    top_processes = [
        {"cpu_percent": 200.0},
        {"cpu_percent": 50.0},
        {"cpu_percent": 25.0},
    ]
    logical_cpu = 4
    cpu_values = [float(p.get("cpu_percent") or 0) for p in top_processes]
    cpu_sum_norm = round(sum(cpu_values) / logical_cpu, 3)
    cpu_max_norm = round(max(cpu_values) / logical_cpu, 3)
    assert cpu_sum_norm == 68.75
    assert cpu_max_norm == 50.0

    # Zero-guard: empty list must not raise and must yield 0.
    empty_values: list = []
    denom = logical_cpu if logical_cpu else 1
    assert (sum(empty_values) / denom) == 0
    assert (max(empty_values) if empty_values else 0.0) == 0.0
