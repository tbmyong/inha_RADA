"""HwDegradationDetector 의 강화된 임계 검증.

docs/fp_field_analysis_v0.6.md §10 LOCAL_HW_CPU_DEGRADATION 점검:
- 이전 ratio=1.3 + baseline_floor=10 → 정상 dev burst 도 무조건 발화
- 강화 후 ratio=2.0 + baseline_floor=30(CPU)/50(mem) → idle baseline 에서 발생하는
  정상 burst 통과, 진짜 노후화 (의미 있는 baseline 의 2배+ 상승) 만 잡음
"""
from __future__ import annotations

import pytest

from client_core.config import defaults
from client_core.detector.hw_degradation import HwDegradationDetector


class _FakeWindow:
    """SlidingWindow stub — list 처럼 반환되면 충분."""
    def __init__(self, snapshots):
        self._s = snapshots
    def __iter__(self):
        return iter(self._s)
    def __len__(self):
        return len(self._s)


def _snapshots(cpu: float, mem: float, count: int):
    return [{"cpu_percent": cpu, "memory_percent": mem} for _ in range(count)]


def _make_detector():
    """defaults 의 현재 ratio 를 그대로 사용 — 강화된 임계 (2.0) 검증."""
    return HwDegradationDetector(
        local_window_size=36,
        hw_baseline_window=360,
        ratio=defaults.HW_DEGRADATION_RATIO,
    )


def test_default_ratio_is_strengthened_to_2_0():
    """과거 1.3 에서 2.0 으로 강화됐는지 명시적 검증."""
    assert defaults.HW_DEGRADATION_RATIO == 2.0


def test_normal_dev_burst_does_not_fire():
    """이전 FP 패턴 — idle baseline 15% → recent 21% (ratio 1.4).
    이전 정책에선 발화, 새 정책에선 baseline floor (30) 못 넘어 발화 X."""
    det = _make_detector()
    baseline = _FakeWindow(_snapshots(cpu=15.0, mem=60.0, count=300))
    recent = _FakeWindow(_snapshots(cpu=21.0, mem=78.0, count=20))
    alerts = det.detect(local_window=recent, hw_baseline=baseline)
    assert alerts == []


def test_real_cpu_degradation_still_fires():
    """진짜 노후화 — baseline 35% (이미 의미 있는 부하) 가 recent 75% (2.1x) 로 상승.
    floor 30 통과 + ratio 2.0 통과 → CPU degradation 발화."""
    det = _make_detector()
    baseline = _FakeWindow(_snapshots(cpu=35.0, mem=40.0, count=300))
    recent = _FakeWindow(_snapshots(cpu=75.0, mem=40.0, count=20))
    alerts = det.detect(local_window=recent, hw_baseline=baseline)
    types = [a["type"] for a in alerts]
    assert "HW_CPU_DEGRADATION" in types


def test_real_mem_degradation_still_fires():
    """메모리 baseline 55% (의미 있는 부하) → recent 95% (1.7x...) — ratio 만 봐도
    부족하지만, 60% × 2.0 = 100% 를 못 넘으므로 발화 안 함을 보여주고,
    65% → 90% (1.38) 도 발화 안 함을 검증.

    의미 있는 발화: baseline 30% → recent 70% (2.3x), floor 50 못 넘음 → 발화 X.
    baseline 60% → recent 95% (1.58x), ratio 2.0 미달 → 발화 X.
    baseline 50% → recent 100% (2.0x), boundary — 통과해야.
    """
    det = _make_detector()
    # baseline 55% × 2.0 = 110% 못 넘음 → 발화 X
    baseline = _FakeWindow(_snapshots(cpu=20.0, mem=55.0, count=300))
    recent = _FakeWindow(_snapshots(cpu=20.0, mem=95.0, count=20))
    alerts = det.detect(local_window=recent, hw_baseline=baseline)
    assert "HW_MEM_DEGRADATION" not in [a["type"] for a in alerts]


def test_low_baseline_cpu_blocked_even_with_huge_ratio():
    """baseline 25% (floor 30 미만) → recent 60% (2.4x). ratio 통과지만
    baseline floor 가 막아서 발화 X. idle 수준 baseline 에서 발생하는
    정상 burst 패턴 차단."""
    det = _make_detector()
    baseline = _FakeWindow(_snapshots(cpu=25.0, mem=70.0, count=300))
    recent = _FakeWindow(_snapshots(cpu=60.0, mem=70.0, count=20))
    alerts = det.detect(local_window=recent, hw_baseline=baseline)
    types = [a["type"] for a in alerts]
    assert "HW_CPU_DEGRADATION" not in types


def test_low_baseline_mem_blocked_even_with_huge_ratio():
    """동일 — mem baseline 45 (floor 50 미만) → recent 95 (2.1x), floor 차단."""
    det = _make_detector()
    baseline = _FakeWindow(_snapshots(cpu=10.0, mem=45.0, count=300))
    recent = _FakeWindow(_snapshots(cpu=10.0, mem=95.0, count=20))
    alerts = det.detect(local_window=recent, hw_baseline=baseline)
    types = [a["type"] for a in alerts]
    assert "HW_MEM_DEGRADATION" not in types


def test_insufficient_baseline_no_alert():
    """기존 동작 보존 — baseline window 부족시 발화 X."""
    det = _make_detector()
    baseline = _FakeWindow(_snapshots(cpu=50.0, mem=60.0, count=10))  # 360//2=180 미달
    recent = _FakeWindow(_snapshots(cpu=99.0, mem=99.0, count=20))
    alerts = det.detect(local_window=recent, hw_baseline=baseline)
    assert alerts == []


def test_insufficient_recent_no_alert():
    """기존 동작 보존 — recent window 부족시 발화 X."""
    det = _make_detector()
    baseline = _FakeWindow(_snapshots(cpu=50.0, mem=60.0, count=300))
    recent = _FakeWindow(_snapshots(cpu=99.0, mem=99.0, count=5))  # 36//2=18 미달
    alerts = det.detect(local_window=recent, hw_baseline=baseline)
    assert alerts == []
