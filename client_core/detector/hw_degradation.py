"""HW 노후화 탐지 (기저선 vs 최근 단기 평균).

docs/fp_field_analysis_v0.6.md §10 의 LOCAL_HW_CPU_DEGRADATION 점검 결과
반영. 정상 dev burst (idle baseline 15% → recent 21%) 가 무조건 발화하던
구조가 MEDIUM/NORMAL 404 건의 76% (308 건) 원인이었다.

강화 두 가지:
  1. ratio 1.3 → 2.0 (defaults.HW_DEGRADATION_RATIO)
  2. baseline floor 10 → 30 (CPU) / 50 (memory)
     의미 있게 부하가 있는 baseline 에서만 노후화 의심.

진짜 노후화/throttling (예: idle baseline 35% → recent 70%) 는 그대로
잡고, dev burst (15% → 30%) 같은 정상은 통과시킨다.
"""
from __future__ import annotations

from typing import List

import numpy as np

from ..window import SlidingWindow
from .base import BaseDetector

# 의미 있는 baseline 만 노후화 의심 대상. idle 수준 baseline (10~20%) 에서
# 흔히 발생하는 정상 burst 가 발화하지 않게 floor 를 높였다.
_CPU_BASELINE_FLOOR_PCT = 30.0
_MEM_BASELINE_FLOOR_PCT = 50.0


class HwDegradationDetector(BaseDetector):
    def __init__(
        self,
        local_window_size: int,
        hw_baseline_window: int,
        ratio: float,
    ) -> None:
        self.local_window_size = local_window_size
        self.hw_baseline_window = hw_baseline_window
        self.ratio = ratio

    def detect(
        self,
        local_window: SlidingWindow,
        hw_baseline: SlidingWindow,
    ) -> List[dict]:
        alerts: List[dict] = []
        baseline = list(hw_baseline)
        recent = list(local_window)

        if (
            len(baseline) < self.hw_baseline_window // 2
            or len(recent) < self.local_window_size // 2
        ):
            return alerts

        baseline_cpu = float(np.mean([s["cpu_percent"] for s in baseline]))
        recent_cpu = float(np.mean([s["cpu_percent"] for s in recent]))
        if baseline_cpu > _CPU_BASELINE_FLOOR_PCT and recent_cpu > baseline_cpu * self.ratio:
            alerts.append({
                "layer": 1,
                "type": "HW_CPU_DEGRADATION",
                "severity": "MEDIUM",
                "detail": (
                    f"CPU 기저선 대비 {(recent_cpu/baseline_cpu - 1)*100:.1f}% 상승 "
                    f"(기저선={baseline_cpu:.1f}%, 최근={recent_cpu:.1f}%) "
                    f"→ 노후화 또는 쓰로틀링 의심"
                ),
            })

        baseline_mem = float(np.mean([s["memory_percent"] for s in baseline]))
        recent_mem = float(np.mean([s["memory_percent"] for s in recent]))
        if baseline_mem > _MEM_BASELINE_FLOOR_PCT and recent_mem > baseline_mem * self.ratio:
            alerts.append({
                "layer": 1,
                "type": "HW_MEM_DEGRADATION",
                "severity": "MEDIUM",
                "detail": (
                    f"메모리 기저선 대비 {(recent_mem/baseline_mem - 1)*100:.1f}% 상승 "
                    f"(기저선={baseline_mem:.1f}%, 최근={recent_mem:.1f}%)"
                ),
            })
        return alerts
