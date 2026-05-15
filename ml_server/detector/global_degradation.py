"""전체 PC 노후화 탐지 (Cross-PC 비교, TTL 30초)."""
import time as _time
import numpy as np

from ..config import GLOBAL_DEGRADATION_RATIO, GLOBAL_DEGRADATION_CPU_THR
from ..storage import pc_history_store


def detect_global_hw_degradation() -> dict:
    """전체 PC 최신 메트릭 비교 (TTL: 30초)."""
    now = _time.time()
    TTL = 30.0

    fresh = {
        pc_id: snap for pc_id, snap in pc_history_store.all_pc_latest.items()
        if now - snap.get("_ts", 0) <= TTL
    }

    if len(fresh) < 3:
        return {"detected": False, "reason": f"유효 PC 부족 ({len(fresh)}대, TTL={TTL}초)"}

    total = len(fresh)
    exceed_cpu = sum(
        1 for snap in fresh.values()
        if snap.get("cpu_percent", 0) >= GLOBAL_DEGRADATION_CPU_THR
    )
    exceed_ratio = exceed_cpu / total

    if exceed_ratio >= GLOBAL_DEGRADATION_RATIO:
        avg_cpu = np.mean([s.get("cpu_percent", 0) for s in fresh.values()])
        return {
            "detected":      True,
            "exceed_count":  exceed_cpu,
            "total_pcs":     total,
            "exceed_ratio":  round(exceed_ratio, 2),
            "avg_cpu":       round(float(avg_cpu), 1),
            "detail":        (f"전체 {total}대 중 {exceed_cpu}대 ({exceed_ratio*100:.0f}%)가 "
                              f"CPU {GLOBAL_DEGRADATION_CPU_THR}% 초과 "
                              f"(평균={avg_cpu:.1f}%) → 전체 노후화 또는 고부하 의심"),
        }

    return {
        "detected":     False,
        "exceed_count": exceed_cpu,
        "total_pcs":    total,
        "exceed_ratio": round(exceed_ratio, 2),
    }
