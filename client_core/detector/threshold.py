"""슬롯별 동적 임계값 기반 로컬 경고 (기존 detect_local_alerts)."""
from __future__ import annotations

from typing import Dict, List

from ..timeslot import get_time_slot
from .base import BaseDetector


class ThresholdDetector(BaseDetector):
    def __init__(self, thresholds: Dict[str, dict]) -> None:
        self.thresholds = thresholds

    def detect(self, metrics: dict) -> List[dict]:
        alerts: List[dict] = []
        slot = get_time_slot()
        thresh = self.thresholds[slot]
        gpu = metrics.get("gpu")

        cpu = metrics["cpu_percent"]
        if cpu >= thresh["cpu_critical"]:
            alerts.append({
                "layer": 1,
                "type": "CPU_CRITICAL",
                "severity": "HIGH",
                "detail": f"CPU 임계 초과: {cpu}% (슬롯={slot}, 기준={thresh['cpu_critical']}%)",
            })
        elif cpu >= thresh["cpu_warn"]:
            alerts.append({
                "layer": 1,
                "type": "CPU_HIGH",
                "severity": "MEDIUM",
                "detail": f"CPU 경고: {cpu}% (슬롯={slot}, 기준={thresh['cpu_warn']}%)",
            })

        mem = metrics["memory_percent"]
        if mem >= thresh["mem_critical"]:
            alerts.append({
                "layer": 1,
                "type": "MEM_CRITICAL",
                "severity": "HIGH",
                "detail": f"메모리 임계 초과: {mem}% (슬롯={slot})",
            })
        elif mem >= thresh["mem_warn"]:
            alerts.append({
                "layer": 1,
                "type": "MEM_HIGH",
                "severity": "MEDIUM",
                "detail": f"메모리 경고: {mem}% (슬롯={slot})",
            })

        if gpu:
            if gpu["load_percent"] >= thresh["gpu_warn"]:
                alerts.append({
                    "layer": 1,
                    "type": "GPU_HIGH",
                    "severity": "MEDIUM",
                    "detail": f"GPU 경고: {gpu['load_percent']}% (슬롯={slot})",
                })
            temp = gpu.get("temperature")
            if temp and temp >= thresh["gpu_temp"]:
                alerts.append({
                    "layer": 1,
                    "type": "GPU_OVERHEAT",
                    "severity": "HIGH",
                    "detail": f"GPU 과열: {temp}°C → 쓰로틀링 의심 (기준={thresh['gpu_temp']}°C)",
                })
            if (gpu["load_percent"] >= 70
                    and gpu.get("tensor_core_active") is not None
                    and gpu["tensor_core_active"] == 0):
                alerts.append({
                    "layer": 1,
                    "type": "TENSOR_CORE_ZERO",
                    "severity": "HIGH",
                    "detail": f"GPU {gpu['load_percent']}% + 텐서코어 0% (채굴 의심)",
                })
        return alerts
