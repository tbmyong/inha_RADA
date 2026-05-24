"""PC 단기/장기 히스토리 저장소 + 전체 PC 최신 메트릭.

확장 (v0.6):
- ``pc_minute_aggregates``: PC 별 1분 aggregate (mean/std/max) × 180 entry (3h 윈도우).
  카테고리 패턴 evaluator 가 sustained 30분~3h 윈도우를 평가하기 위해 사용.
- ``pc_category_state``: 카테고리 boolean 들의 동시 만족 시작 시각을 PC 별로 보관 (sustained_minutes 계산용).
"""
import time as _time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from ..config import WINDOW_SIZE, TRAIN_WINDOW

# 단기 히스토리 (패턴 분석)
pc_history: Dict[str, deque] = {}

# 장기 히스토리 (학습용) — pc_id → {slot → deque}
pc_train_history: Dict[str, Dict[str, deque]] = {}

# 전체 PC 최신 메트릭 (Cross-PC 비교용)
all_pc_latest: Dict[str, dict] = {}


# ──────────────────────────────────────────
# 신규: 1분 aggregate × 180 (3h) 윈도우
# ──────────────────────────────────────────
# pc_id → deque[ aggregate_entry ]
# aggregate_entry = {
#   "ts": float (epoch sec, 1분 슬롯 시작),
#   "cpu_mean", "cpu_std", "cpu_max",
#   "gpu_mean", "gpu_std", "gpu_max",
#   "mem_used_gb_mean",
#   "disk_io_mb_mean",
#   "outbound_mb_mean", "outbound_mb_std",
#   "inbound_mb_mean",
#   "user_idle_ms_max",
#   "gpu_power_w_mean", "gpu_power_w_std",
#   "vram_used_mb_mean",
#   "external_endpoints": set[str],  # 1분간 관측된 외부 IP 집합
#   "samples": int,
# }
AGGREGATE_WINDOW_MAX = 180  # 1분 × 180 = 3h
pc_minute_aggregates: Dict[str, Deque[dict]] = {}

# 1분 누적 버퍼 (raw 5초 단위 샘플 누적). 매 1분이 지나면 aggregate 로 굳혀
# pc_minute_aggregates 로 옮긴 뒤 비운다.
# pc_id → { "slot_start": float (epoch sec), "samples": list[dict] }
_pc_minute_buffer: Dict[str, Dict[str, Any]] = {}

# P1-2 dos spike sustained count tracker.
# pc_id → int (consecutive spikes that met both ratio + absolute floor).
# Reset to 0 once a sample fails either condition.
dos_spike_streak: Dict[str, int] = {}

# P1-3 last anomaly persist timestamp per (pc_id, anomaly_type) — used by
# Spring AlertService for cooldown, also exposed for ML-side analytics.
# Stored as Dict[Tuple[str,str], float (epoch sec)].
# 카테고리 boolean 들의 sustained 추적용 상태.
# pc_id → {
#   "all_three_since": Optional[float],  # 3 카테고리 동시 충족 시작 epoch
#   "any_two_since":   Optional[float],  # 2 카테고리 이상 충족 시작 epoch
#   "any_one_since":   Optional[float],  # 1 카테고리 이상 충족 시작 epoch
#   "last_cats_count": int,
#   "last_ts":         float,
# }
pc_category_state: Dict[str, dict] = {}


def ensure_pc_history(pc_id: str) -> deque:
    if pc_id not in pc_history:
        pc_history[pc_id] = deque(maxlen=WINDOW_SIZE)
    return pc_history[pc_id]


def update_train_history(pc_id: str, slot: str, snapshot: dict) -> None:
    if pc_id not in pc_train_history:
        pc_train_history[pc_id] = {}
    if slot not in pc_train_history[pc_id]:
        pc_train_history[pc_id][slot] = deque(maxlen=TRAIN_WINDOW)
    pc_train_history[pc_id][slot].append(snapshot)


def _parse_ts(snapshot: dict) -> float:
    """snapshot 의 timestamp(ISO 또는 epoch) 를 epoch 초로 반환. 실패 시 현재시각."""
    ts_raw = snapshot.get("timestamp")
    if isinstance(ts_raw, (int, float)):
        return float(ts_raw)
    if isinstance(ts_raw, str):
        try:
            import datetime as _dt
            return _dt.datetime.fromisoformat(ts_raw).timestamp()
        except Exception:
            return _time.time()
    return _time.time()


def _flush_minute_buffer(pc_id: str, slot_start: float, samples: List[dict]) -> None:
    """1분 버퍼를 aggregate 로 굳혀 deque 에 추가."""
    import statistics
    if not samples:
        return

    def _vals(key: str) -> List[float]:
        out = []
        for s in samples:
            v = s.get(key)
            if v is None:
                continue
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
        return out

    def _agg(vals: List[float]) -> Dict[str, float]:
        if not vals:
            return {"mean": 0.0, "std": 0.0, "max": 0.0}
        mean = statistics.mean(vals)
        std = statistics.stdev(vals) if len(vals) >= 2 else 0.0
        return {"mean": mean, "std": std, "max": max(vals)}

    cpu = _agg(_vals("cpu_percent"))
    gpu = _agg(_vals("gpu_percent"))
    power = _agg(_vals("gpu_power_w"))
    outbound = _agg(_vals("outbound_mb"))
    inbound = _agg(_vals("inbound_mb"))
    vram = _agg(_vals("gpu_vram_mb"))
    mem_used_gb_vals = _vals("memory_used_gb")
    mem_used_gb_mean = statistics.mean(mem_used_gb_vals) if mem_used_gb_vals else 0.0
    disk_vals = [
        float(s.get("disk_read_mb") or 0.0) + float(s.get("disk_write_mb") or 0.0)
        for s in samples
    ]
    disk_mean = statistics.mean(disk_vals) if disk_vals else 0.0
    idle_vals = _vals("user_idle_ms")
    idle_max = max(idle_vals) if idle_vals else 0.0

    # external endpoints (이 1분 내 모든 외부 IP)
    endpoints: set = set()
    for s in samples:
        for ep in s.get("external_endpoints") or []:
            if isinstance(ep, str) and ep:
                endpoints.add(ep)

    entry = {
        "ts": float(slot_start),
        "cpu_mean": cpu["mean"], "cpu_std": cpu["std"], "cpu_max": cpu["max"],
        "gpu_mean": gpu["mean"], "gpu_std": gpu["std"], "gpu_max": gpu["max"],
        "mem_used_gb_mean": mem_used_gb_mean,
        "disk_io_mb_mean": disk_mean,
        "outbound_mb_mean": outbound["mean"], "outbound_mb_std": outbound["std"],
        "inbound_mb_mean": inbound["mean"],
        "vram_used_mb_mean": vram["mean"],
        "gpu_power_w_mean": power["mean"], "gpu_power_w_std": power["std"],
        "user_idle_ms_max": idle_max,
        "external_endpoints": endpoints,
        "samples": len(samples),
    }

    dq = pc_minute_aggregates.setdefault(
        pc_id, deque(maxlen=AGGREGATE_WINDOW_MAX)
    )
    dq.append(entry)


def append_snapshot_for_aggregate(pc_id: str, snapshot: dict,
                                  external_endpoints: Optional[List[str]] = None,
                                  user_idle_ms: Optional[float] = None,
                                  memory_used_gb: Optional[float] = None) -> None:
    """5초 단위 snapshot 을 1분 버퍼에 추가하고, 1분 경과 시 aggregate 로 굳힌다.

    snapshot 은 feature_builder.make_snapshot 결과 + 옵션 필드.
    """
    ts = _parse_ts(snapshot)
    minute = int(ts // 60) * 60

    buf = _pc_minute_buffer.setdefault(pc_id, {"slot_start": float(minute), "samples": []})
    if buf["slot_start"] != float(minute):
        # 이전 분 종료 — flush
        _flush_minute_buffer(pc_id, buf["slot_start"], buf["samples"])
        buf["slot_start"] = float(minute)
        buf["samples"] = []

    enriched = dict(snapshot)
    if external_endpoints is not None:
        enriched["external_endpoints"] = list(external_endpoints)
    if user_idle_ms is not None:
        enriched["user_idle_ms"] = user_idle_ms
    if memory_used_gb is not None:
        enriched["memory_used_gb"] = memory_used_gb
    buf["samples"].append(enriched)


def force_flush_minute_buffer(pc_id: str) -> None:
    """테스트 / 강제 flush. 현재 버퍼를 즉시 aggregate 로 굳힘."""
    buf = _pc_minute_buffer.get(pc_id)
    if not buf or not buf["samples"]:
        return
    _flush_minute_buffer(pc_id, buf["slot_start"], buf["samples"])
    buf["samples"] = []


def get_aggregate_window(pc_id: str, minutes: int) -> List[dict]:
    """PC 의 최근 N분 aggregate 엔트리 리스트 (오래된 → 최신 순). N>180 이면 180 으로 제한."""
    if minutes <= 0:
        return []
    if minutes > AGGREGATE_WINDOW_MAX:
        minutes = AGGREGATE_WINDOW_MAX
    dq = pc_minute_aggregates.get(pc_id)
    if not dq:
        return []
    if len(dq) <= minutes:
        return list(dq)
    return list(dq)[-minutes:]


def get_category_state(pc_id: str) -> dict:
    return pc_category_state.setdefault(pc_id, {
        "all_three_since": None,
        "any_two_since": None,
        "any_one_since": None,
        "last_cats_count": 0,
        "last_ts": 0.0,
    })


def reset_all_state() -> None:
    """테스트용 — 모든 글로벌 dict 초기화."""
    pc_history.clear()
    pc_train_history.clear()
    all_pc_latest.clear()
    pc_minute_aggregates.clear()
    _pc_minute_buffer.clear()
    pc_category_state.clear()
    dos_spike_streak.clear()
