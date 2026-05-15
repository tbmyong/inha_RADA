"""HW 노후화 탐지 (기저선 vs 최근 단기 평균)."""
from __future__ import annotations

from typing import List

import numpy as np

from ..window import SlidingWindow
from .base import BaseDetector


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
        if baseline_cpu > 10 and recent_cpu > baseline_cpu * self.ratio:
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
        if baseline_mem > 10 and recent_mem > baseline_mem * self.ratio:
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
