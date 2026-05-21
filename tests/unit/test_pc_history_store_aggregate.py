"""pc_history_store 의 1분 aggregate × 180 윈도우 동작 검증."""
from __future__ import annotations
import datetime as _dt

import pytest

from ml_server.storage import pc_history_store


@pytest.fixture(autouse=True)
def _reset():
    pc_history_store.reset_all_state()
    yield
    pc_history_store.reset_all_state()


# Windows의 timestamp() 가 pre-1970 local 시간에서 OSError 를 던지므로
# 충분히 미래의 epoch base 를 사용한다. base = 2020-01-01 00:00:00 UTC.
_BASE_EPOCH = 1577836800.0


def _snap(ts_epoch: float, cpu: float = 50.0, gpu: float = 0.0,
          outbound: float = 0.0, inbound: float = 0.0,
          power: float = 0.0, vram: float = 0.0,
          disk_r: float = 0.0, disk_w: float = 0.0) -> dict:
    return {
        "timestamp": _dt.datetime.fromtimestamp(_BASE_EPOCH + ts_epoch).isoformat(),
        "cpu_percent": cpu,
        "gpu_percent": gpu,
        "outbound_mb": outbound,
        "inbound_mb": inbound,
        "gpu_power_w": power,
        "gpu_vram_mb": vram,
        "disk_read_mb": disk_r,
        "disk_write_mb": disk_w,
    }


def test_aggregate_window_empty_initially():
    assert pc_history_store.get_aggregate_window("PC1", 30) == []


def test_one_minute_flush_via_next_minute_sample():
    pc = "PC1"
    # 12 samples in minute 60
    for i in range(12):
        pc_history_store.append_snapshot_for_aggregate(
            pc, _snap(60 + i * 5, cpu=90.0, gpu=95.0))
    # No flush yet (still inside minute 60)
    assert len(pc_history_store.get_aggregate_window(pc, 180)) == 0
    # Add a sample in minute 120 → triggers flush of minute 60
    pc_history_store.append_snapshot_for_aggregate(pc, _snap(120, cpu=10))
    window = pc_history_store.get_aggregate_window(pc, 180)
    assert len(window) == 1
    e = window[0]
    assert e["cpu_mean"] == pytest.approx(90.0)
    assert e["gpu_mean"] == pytest.approx(95.0)
    assert e["samples"] == 12


def test_force_flush():
    pc = "PC1"
    for i in range(3):
        pc_history_store.append_snapshot_for_aggregate(
            pc, _snap(60 + i, cpu=80.0, gpu=70.0))
    pc_history_store.force_flush_minute_buffer(pc)
    win = pc_history_store.get_aggregate_window(pc, 1)
    assert len(win) == 1
    assert win[0]["cpu_mean"] == pytest.approx(80.0)


def test_window_cap_180():
    pc = "PC1"
    # Build 200 distinct minutes, 1 sample each. Each new minute flushes previous.
    for minute in range(200):
        pc_history_store.append_snapshot_for_aggregate(
            pc, _snap(minute * 60, cpu=float(minute % 100)))
    pc_history_store.force_flush_minute_buffer(pc)
    win = pc_history_store.get_aggregate_window(pc, 180)
    # cap at 180 entries
    assert len(win) == 180


def test_external_endpoints_aggregated():
    pc = "PC1"
    pc_history_store.append_snapshot_for_aggregate(
        pc, _snap(60), external_endpoints=["1.1.1.1", "2.2.2.2"])
    pc_history_store.append_snapshot_for_aggregate(
        pc, _snap(65), external_endpoints=["1.1.1.1"])
    pc_history_store.force_flush_minute_buffer(pc)
    win = pc_history_store.get_aggregate_window(pc, 1)
    assert "1.1.1.1" in win[0]["external_endpoints"]
    assert "2.2.2.2" in win[0]["external_endpoints"]


def test_user_idle_ms_max():
    pc = "PC1"
    pc_history_store.append_snapshot_for_aggregate(pc, _snap(60), user_idle_ms=1000)
    pc_history_store.append_snapshot_for_aggregate(pc, _snap(65), user_idle_ms=5000)
    pc_history_store.force_flush_minute_buffer(pc)
    win = pc_history_store.get_aggregate_window(pc, 1)
    assert win[0]["user_idle_ms_max"] == 5000


def test_memory_used_gb_mean():
    pc = "PC1"
    pc_history_store.append_snapshot_for_aggregate(pc, _snap(60), memory_used_gb=2.0)
    pc_history_store.append_snapshot_for_aggregate(pc, _snap(65), memory_used_gb=4.0)
    pc_history_store.force_flush_minute_buffer(pc)
    win = pc_history_store.get_aggregate_window(pc, 1)
    assert win[0]["mem_used_gb_mean"] == pytest.approx(3.0)


def test_category_state_default():
    state = pc_history_store.get_category_state("PC1")
    assert state["last_cats_count"] == 0
    assert state["all_three_since"] is None
