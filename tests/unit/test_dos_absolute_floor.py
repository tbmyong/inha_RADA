"""P1-2 — DOS / network spike absolute floor + sustained count.

docs/fp_field_analysis_v0.6.md §7-P1-2.

Before P1-2, dos_spike fired purely on (inbound_mb > avg_inbound * N).
With baseline 0.03 MB a 2.5 MB download burst is an 80× ratio and was
flagged as dos. P1-2 requires BOTH:
  - ratio > dos_ratio (per-slot threshold, unchanged)
  - inbound_mb >= dos_detection.min_inbound_mb_per_5s (absolute floor)
  - AND the (ratio + absolute) pair has held for ``min_sustained_count``
    consecutive samples (anti-single-spike).
"""
from __future__ import annotations

from collections import deque

import pytest

from ml_server.model.requests import MetricsRequest
from ml_server.policy import reload_policies
from ml_server.scorer.signal_extractor import extract_signals
from ml_server.storage import pc_history_store


@pytest.fixture(autouse=True)
def _reset_state():
    reload_policies()
    pc_history_store.reset_all_state()
    yield
    pc_history_store.reset_all_state()


def _history(avg_inbound: float, n: int = 12) -> deque:
    """Build a history deque with constant inbound_mb so avg = avg_inbound."""
    dq: deque = deque()
    for _ in range(n):
        dq.append({
            "cpu_percent": 5.0, "memory_percent": 30.0,
            "gpu_percent": 0.0, "gpu_vram_mb": 0.0, "gpu_power_w": 0.0,
            "inbound_mb": avg_inbound, "outbound_mb": 0.1,
            "external_packet_count": 0, "disk_read_mb": 0.0,
            "disk_write_mb": 0.0, "top_processes": [],
        })
    return dq


def _metrics(inbound_mb: float, pc_id: str = "pc-dos") -> MetricsRequest:
    return MetricsRequest(
        pc_id=pc_id,
        timestamp="2026-05-23T10:00:00+09:00",
        cpu_percent=5.0,
        memory_percent=30.0,
        disk_read_mb=0.0,
        disk_write_mb=0.0,
        inbound_mb=inbound_mb,
        outbound_mb=0.1,
        external_packet_count=0,
        gpu={"name": "x", "load_percent": 0, "memory_used_mb": 0,
             "memory_total_mb": 1, "memory_percent": 0},
        local_alerts=[],
    )


def test_high_ratio_low_absolute_does_not_fire():
    """baseline 0.03MB + spike 2.5MB (80× ratio, but < 20MB floor) → no fire."""
    history = _history(avg_inbound=0.03)
    # Single sample below floor.
    sigs = extract_signals(_metrics(inbound_mb=2.5), history, "free")["signals"]
    assert sigs["dos_spike"] is False


def test_high_ratio_below_floor_repeated_still_no_fire():
    """Even sustained, samples below absolute floor never fire."""
    history = _history(avg_inbound=0.03)
    for _ in range(5):
        sigs = extract_signals(_metrics(inbound_mb=2.5), history, "free")["signals"]
        assert sigs["dos_spike"] is False


def test_ratio_and_absolute_single_hit_not_yet_sustained():
    """Ratio + absolute floor met on a single sample is below default
    min_sustained_count=2 — no fire on the first hit."""
    history = _history(avg_inbound=0.5)  # 0.5 * 15 = 7.5 → 25 > 7.5 ratio ok
    sigs = extract_signals(_metrics(inbound_mb=25.0), history, "free")["signals"]
    assert sigs["dos_spike"] is False  # streak=1 < 2


def test_ratio_and_absolute_sustained_two_hits_fires():
    """Second consecutive hit reaches min_sustained_count=2 → fire."""
    history = _history(avg_inbound=0.5)
    m = _metrics(inbound_mb=25.0)
    extract_signals(m, history, "free")  # streak=1
    sigs = extract_signals(m, history, "free")["signals"]  # streak=2
    assert sigs["dos_spike"] is True


def test_streak_resets_after_normal_sample():
    """One sample below floor resets the streak."""
    history = _history(avg_inbound=0.5)
    m_hit = _metrics(inbound_mb=25.0)
    m_miss = _metrics(inbound_mb=0.5)  # ratio fails
    extract_signals(m_hit, history, "free")  # streak=1
    extract_signals(m_miss, history, "free")  # reset
    sigs = extract_signals(m_hit, history, "free")["signals"]  # streak=1 again
    assert sigs["dos_spike"] is False


def test_dos_floor_yaml_keys_loaded():
    """The DosDetection dataclass exposes the YAML values."""
    from ml_server.policy import get_scoring_policy
    p = get_scoring_policy()
    assert p.dos_detection.min_inbound_mb_per_5s == pytest.approx(20.0)
    assert p.dos_detection.min_sustained_count == 2
