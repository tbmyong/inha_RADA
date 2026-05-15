"""슬롯 무관 절대 임계값 초과 (기존 detect_absolute_breach)."""
from __future__ import annotations

from typing import List

from .base import BaseDetector


class AbsoluteBreachDetector(BaseDetector):
    def __init__(self, absolute_thresholds: dict) -> None:
        self.absolute = absolute_thresholds

    def detect(self, metrics: dict) -> List[dict]:
        alerts: List[dict] = []
        gpu = metrics.get("gpu")

        if metrics["cpu_percent"] >= self.absolute["cpu_percent"]:
            alerts.append({
                "type": "ABSOLUTE_CPU",
                "severity": "HIGH",
                "detail": (
                    f"CPU 절대 임계 초과: {metrics['cpu_percent']}% "
                    f"(기준={self.absolute['cpu_percent']}%)"
                ),
            })
        if metrics["memory_percent"] >= self.absolute["mem_percent"]:
            alerts.append({
                "type": "ABSOLUTE_MEM",
                "severity": "HIGH",
                "detail": f"메모리 절대 임계 초과: {metrics['memory_percent']}%",
            })
        if gpu:
            if gpu["load_percent"] >= self.absolute["gpu_percent"]:
                alerts.append({
                    "type": "ABSOLUTE_GPU",
                    "severity": "HIGH",
                    "detail": f"GPU 절대 임계 초과: {gpu['load_percent']}%",
                })
            temp = gpu.get("temperature")
            if temp and temp >= self.absolute["gpu_temp"]:
                alerts.append({
                    "type": "ABSOLUTE_GPU_TEMP",
                    "severity": "HIGH",
                    "detail": f"GPU 온도 절대 임계: {temp}°C → 하드웨어 손상 위험",
                })
        return alerts
