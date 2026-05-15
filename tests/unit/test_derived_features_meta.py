"""CpuMemCollector 메타 키 (logical/physical CPU, uptime) 검증."""
from __future__ import annotations

from agent_core.collector.cpu_mem import CpuMemCollector


def test_cpu_mem_meta_keys_present():
    c = CpuMemCollector(cpu_interval=0.0)
    out = c.collect()
    for key in ("logical_cpu_count", "physical_cpu_count", "uptime_sec"):
        assert key in out, f"missing meta key: {key}"


def test_cpu_mem_meta_types():
    c = CpuMemCollector(cpu_interval=0.0)
    out = c.collect()
    assert isinstance(out["logical_cpu_count"], int)
    assert isinstance(out["physical_cpu_count"], int)
    assert isinstance(out["uptime_sec"], int)


def test_uptime_non_negative():
    c = CpuMemCollector(cpu_interval=0.0)
    out = c.collect()
    assert out["uptime_sec"] >= 0


def test_logical_cpu_positive():
    c = CpuMemCollector(cpu_interval=0.0)
    out = c.collect()
    # 정상 환경에서 1 이상
    assert out["logical_cpu_count"] >= 1
