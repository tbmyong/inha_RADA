"""IQR 박스플롯 기반 로컬 이상 신호 (기존 compute_boxplot_signal)."""
from __future__ import annotations

from typing import Tuple

import numpy as np

from ..window import SlidingWindow


class BoxplotDetector:
    """ShortTermWindow에 IQR(1.5*IQR) 적용 → 현재 스냅샷이 이상치인지 판단.

    Chen et al. (2023) BS-iForest 보조 신호로 ML 서버에 전달.
    """

    def __init__(self, min_window: int = 12) -> None:
        self.min_window = min_window

    def compute(self, window: SlidingWindow) -> dict:
        items = list(window)
        if len(items) < self.min_window:
            return {"available": False, "reason": "윈도우 데이터 부족"}

        cpu_vals = np.array([s["cpu_percent"] for s in items])
        mem_vals = np.array([s["memory_percent"] for s in items])

        current = items[-1]
        cpu_out, cpu_dev = self._is_iqr_outlier(cpu_vals[:-1], current["cpu_percent"])
        mem_out, mem_dev = self._is_iqr_outlier(mem_vals[:-1], current["memory_percent"])

        return {
            "available": True,
            "cpu_iqr_outlier": cpu_out,
            "cpu_deviation": cpu_dev,
            "mem_iqr_outlier": mem_out,
            "mem_deviation": mem_dev,
            "window_size": len(items),
            "cpu_q1": round(float(np.percentile(cpu_vals, 25)), 1),
            "cpu_q3": round(float(np.percentile(cpu_vals, 75)), 1),
            "mem_q1": round(float(np.percentile(mem_vals, 25)), 1),
            "mem_q3": round(float(np.percentile(mem_vals, 75)), 1),
        }

    @staticmethod
    def _is_iqr_outlier(arr: np.ndarray, current: float) -> Tuple[bool, float]:
        q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
        iqr = q3 - q1
        upper = q3 + 1.5 * iqr
        lower = q1 - 1.5 * iqr
        is_out = bool(current > upper or current < lower)
        deviation = max(0.0, (current - upper) / (iqr + 0.001)) if iqr > 0 else 0.0
        return is_out, round(float(deviation), 3)
