"""카테고리 패턴 evaluator (Resource / Network / System).

명세: ``docs/cryptojacking_detection_patterns.md`` 8.2 / 8.3 절.

각 evaluator 는 PC 별 1분 aggregate 시계열 (``history_window``) +
현재 스냅샷 (``current_snapshot``) + 정책 설정 (``config``) 을 받아
``CategoryResult`` 를 반환한다.

본 모듈은 catalog 8.1 절의 "보류" 항목 (R6/R9/N1/N6/S2/S5) 은 stub 만 두고
실제 평가 로직은 두지 않는다 — config 에서 활성화돼도 항상 False.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CategoryResult:
    abnormal: bool
    triggered_patterns: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "abnormal": bool(self.abnormal),
            "triggered_patterns": list(self.triggered_patterns),
            "detail": dict(self.detail),
        }


def _t(config: Dict[str, Any], pattern: str) -> Optional[Dict[str, Any]]:
    """category_patterns.<group>.<pattern>.threshold 를 fetch.

    config 는 ``category_patterns`` dict 의 sub-group (resource/network/system) 자체.
    pattern entry 가 없거나 ``enabled: false`` 면 None.
    """
    entry = config.get(pattern) if config else None
    if not isinstance(entry, dict):
        return None
    if entry.get("enabled") is False:
        return None
    th = entry.get("threshold") or {}
    return th if isinstance(th, dict) else {}


def _window_minutes_satisfied(history_window: List[dict], predicate, required_min: int) -> bool:
    """history_window (1분 aggregate × N, 오래된→최신) 의 최신 required_min 분 모두 predicate True 인지."""
    if required_min <= 0:
        return True
    if len(history_window) < required_min:
        return False
    tail = history_window[-required_min:]
    return all(predicate(e) for e in tail)


# ──────────────────────────────────────────
# Resource
# ──────────────────────────────────────────
def evaluate_resource_pattern(history_window: List[dict],
                              current_snapshot: Dict[str, Any],
                              config: Dict[str, Any]) -> CategoryResult:
    """R1/R2/R3/R4/R5/R7/R8 평가. R6/R9 는 stub (catalog 8.1 절 보류)."""
    triggered: List[str] = []
    detail: Dict[str, Any] = {}
    cfg = (config or {}).get("resource") or {}

    # R1: CPU >= 90% AND std < 5% sustained
    th = _t(cfg, "R1_cpu_flat_sustained")
    if th is not None:
        cpu_pct = float(th.get("cpu_pct", 90))
        std_max = float(th.get("std", 5))
        win = int(th.get("window_min", 30))
        if _window_minutes_satisfied(
            history_window,
            lambda e: float(e.get("cpu_mean", 0)) >= cpu_pct and float(e.get("cpu_std", 0)) < std_max,
            win,
        ):
            triggered.append("R1")

    # R2: GPU >= 90% AND std < 5% sustained
    th = _t(cfg, "R2_gpu_flat_sustained")
    if th is not None:
        gpu_pct = float(th.get("gpu_pct", 90))
        std_max = float(th.get("std", 5))
        win = int(th.get("window_min", 30))
        if _window_minutes_satisfied(
            history_window,
            lambda e: float(e.get("gpu_mean", 0)) >= gpu_pct and float(e.get("gpu_std", 0)) < std_max,
            win,
        ):
            triggered.append("R2")

    # R3: CPU >= 90% AND GPU >= 90% sustained
    th = _t(cfg, "R3_cpu_gpu_both_high")
    if th is not None:
        cpu_pct = float(th.get("cpu_pct", 90))
        gpu_pct = float(th.get("gpu_pct", 90))
        win = int(th.get("window_min", 30))
        if _window_minutes_satisfied(
            history_window,
            lambda e: float(e.get("cpu_mean", 0)) >= cpu_pct and float(e.get("gpu_mean", 0)) >= gpu_pct,
            win,
        ):
            triggered.append("R3")

    # R4: GPU >= 90% AND CPU < 15% sustained (asymmetric)
    th = _t(cfg, "R4_gpu_only_asymmetric")
    if th is not None:
        gpu_pct = float(th.get("gpu_pct", 90))
        cpu_max = float(th.get("cpu_pct_max", 15))
        win = int(th.get("window_min", 30))
        if _window_minutes_satisfied(
            history_window,
            lambda e: float(e.get("gpu_mean", 0)) >= gpu_pct and float(e.get("cpu_mean", 0)) < cpu_max,
            win,
        ):
            triggered.append("R4")

    # R5: power std < 5W AND mean >= 70% of TDP sustained (only if gpu_power_w_mean > 0)
    th = _t(cfg, "R5_power_flatline")
    if th is not None:
        std_max = float(th.get("power_std_w", 5))
        pct_of_tdp = float(th.get("power_pct_of_tdp", 70))
        tdp_w = float(th.get("tdp_w", 250))  # default TDP guess
        threshold_mean = tdp_w * (pct_of_tdp / 100.0)
        win = int(th.get("window_min", 30))
        def _r5(e):
            mean = float(e.get("gpu_power_w_mean", 0) or 0)
            std = float(e.get("gpu_power_w_std", 0) or 0)
            return mean >= threshold_mean and std < std_max and mean > 0
        if _window_minutes_satisfied(history_window, _r5, win):
            triggered.append("R5")

    # R6 stub: tensor_core 비대칭 — 보류
    th = _t(cfg, "R6_sm_no_tensor")
    if th is not None:
        detail["R6_stubbed"] = True  # 평가하지 않음

    # R7: VRAM used < 1GB AND GPU compute >= 90% sustained
    th = _t(cfg, "R7_vram_low_compute_high")
    if th is not None:
        vram_max_mb = float(th.get("vram_used_mb_max", 1024))
        gpu_pct = float(th.get("gpu_pct", 90))
        win = int(th.get("window_min", 30))
        if _window_minutes_satisfied(
            history_window,
            lambda e: (float(e.get("vram_used_mb_mean", 0) or 0) < vram_max_mb
                       and float(e.get("gpu_mean", 0)) >= gpu_pct),
            win,
        ):
            triggered.append("R7")

    # R8: mem_used_gb < 4 AND GPU >= 90% sustained
    th = _t(cfg, "R8_mem_idle_compute_high")
    if th is not None:
        mem_max_gb = float(th.get("mem_used_gb_max", 4))
        gpu_pct = float(th.get("gpu_pct", 90))
        win = int(th.get("window_min", 30))
        if _window_minutes_satisfied(
            history_window,
            lambda e: (float(e.get("mem_used_gb_mean", 0) or 0) < mem_max_gb
                       and float(e.get("gpu_mean", 0)) >= gpu_pct),
            win,
        ):
            triggered.append("R8")

    # R9 stub: per-core CPU — 보류
    th = _t(cfg, "R9_single_core_full")
    if th is not None:
        detail["R9_stubbed"] = True

    return CategoryResult(
        abnormal=bool(triggered),
        triggered_patterns=triggered,
        detail=detail,
    )


# ──────────────────────────────────────────
# Network
# ──────────────────────────────────────────
def evaluate_network_pattern(history_window: List[dict],
                             current_snapshot: Dict[str, Any],
                             config: Dict[str, Any]) -> CategoryResult:
    """N2/N4/N5 평가. N1/N6 는 stub (catalog 8.1 절 보류)."""
    triggered: List[str] = []
    detail: Dict[str, Any] = {}
    cfg = (config or {}).get("network") or {}

    # N1 stub
    th = _t(cfg, "N1_stratum_periodicity")
    if th is not None:
        detail["N1_stubbed"] = True

    # N2: 동일 외부 endpoint 가 최근 N 분 동안 매 분 등장
    th = _t(cfg, "N2_external_ip_persistent")
    if th is not None:
        win = int(th.get("same_endpoint_minutes", 30))
        if len(history_window) >= win:
            tail = history_window[-win:]
            # 각 분의 endpoint 집합 교집합
            sets = [set(e.get("external_endpoints") or set()) for e in tail]
            if sets and all(sets):
                common = sets[0]
                for s in sets[1:]:
                    common &= s
                if common:
                    triggered.append("N2")
                    detail["N2_endpoints"] = sorted(common)[:5]

    # N4: internal traffic = 0 AND external outbound > 0 sustained
    th = _t(cfg, "N4_internal_zero_external_high")
    if th is not None:
        internal_kb = float(th.get("internal_kb", 0))
        external_mb_min = float(th.get("external_mb_min", 1))
        win = int(th.get("window_min", 30))
        # internal traffic field 미수집 — outbound_mb_mean 만으로 가용한 약식 평가:
        # outbound_mb_mean >= external_mb_min/window 매 분, inbound_mb_mean 거의 0
        def _n4(e):
            ob = float(e.get("outbound_mb_mean", 0))
            ib = float(e.get("inbound_mb_mean", 0))
            return ob >= (external_mb_min / max(win, 1)) and ib <= (internal_kb / 1024.0 + 0.001)
        if _window_minutes_satisfied(history_window, _n4, win):
            triggered.append("N4")

    # N5: outbound CV < 0.3 sustained (low coefficient of variation)
    th = _t(cfg, "N5_outbound_low_cv")
    if th is not None:
        cv_max = float(th.get("cv_max", 0.3))
        win = int(th.get("window_min", 30))
        def _n5(e):
            mean = float(e.get("outbound_mb_mean", 0))
            std = float(e.get("outbound_mb_std", 0))
            if mean <= 0.001:
                return False
            cv = std / mean
            return cv < cv_max
        if _window_minutes_satisfied(history_window, _n5, win):
            triggered.append("N5")

    # N6 stub
    th = _t(cfg, "N6_dns_burst_during_idle")
    if th is not None:
        detail["N6_stubbed"] = True

    return CategoryResult(
        abnormal=bool(triggered),
        triggered_patterns=triggered,
        detail=detail,
    )


# ──────────────────────────────────────────
# System
# ──────────────────────────────────────────
def evaluate_system_pattern(history_window: List[dict],
                            current_snapshot: Dict[str, Any],
                            config: Dict[str, Any]) -> CategoryResult:
    """S1/S3/S4 평가. S2/S5 는 stub (catalog 8.1 절 보류)."""
    triggered: List[str] = []
    detail: Dict[str, Any] = {}
    cfg = (config or {}).get("system") or {}

    # S1: user_idle_ms >= 30분 AND (cpu>=90 OR gpu>=90) sustained
    th = _t(cfg, "S1_user_idle_high_load")
    if th is not None:
        idle_min = float(th.get("user_idle_min", 30))
        cpu_or_gpu = float(th.get("cpu_or_gpu_pct", 90))
        win = int(th.get("window_min", 30))
        idle_ms_threshold = idle_min * 60 * 1000
        def _s1(e):
            cpu = float(e.get("cpu_mean", 0))
            gpu = float(e.get("gpu_mean", 0))
            idle = float(e.get("user_idle_ms_max", 0) or 0)
            return idle >= idle_ms_threshold and (cpu >= cpu_or_gpu or gpu >= cpu_or_gpu)
        if _window_minutes_satisfied(history_window, _s1, win):
            triggered.append("S1")

    # S2 stub (screen_locked) — 보류
    th = _t(cfg, "S2_locked_high_load")
    if th is not None:
        detail["S2_stubbed"] = True

    # S3: cpu/gpu >= 90% AND disk_io (read+write) mean < 1 MB/s sustained
    th = _t(cfg, "S3_high_load_disk_idle")
    if th is not None:
        cpu_or_gpu = float(th.get("cpu_or_gpu_pct", 90))
        disk_max = float(th.get("disk_mb_per_s_max", 1))
        win = int(th.get("window_min", 30))
        def _s3(e):
            cpu = float(e.get("cpu_mean", 0))
            gpu = float(e.get("gpu_mean", 0))
            # disk_io_mb_mean 은 5초 샘플의 평균 (MB per 5s). 환산: 1MB/s ≈ 5MB per 5s.
            # disk_max 는 MB/s 단위. mean 도 동등 단위로 비교하기 위해 그대로 사용한다 (보수적).
            disk = float(e.get("disk_io_mb_mean", 0))
            return (cpu >= cpu_or_gpu or gpu >= cpu_or_gpu) and disk < disk_max
        if _window_minutes_satisfied(history_window, _s3, win):
            triggered.append("S3")

    # S4: cpu/gpu >= 90% AND mem_used_gb < 4 sustained
    th = _t(cfg, "S4_high_load_mem_idle")
    if th is not None:
        cpu_or_gpu = float(th.get("cpu_or_gpu_pct", 90))
        mem_max_gb = float(th.get("mem_used_gb_max", 4))
        win = int(th.get("window_min", 30))
        def _s4(e):
            cpu = float(e.get("cpu_mean", 0))
            gpu = float(e.get("gpu_mean", 0))
            mem = float(e.get("mem_used_gb_mean", 0) or 0)
            return (cpu >= cpu_or_gpu or gpu >= cpu_or_gpu) and mem < mem_max_gb
        if _window_minutes_satisfied(history_window, _s4, win):
            triggered.append("S4")

    # S5 stub
    th = _t(cfg, "S5_process_recreation")
    if th is not None:
        detail["S5_stubbed"] = True

    return CategoryResult(
        abnormal=bool(triggered),
        triggered_patterns=triggered,
        detail=detail,
    )


__all__ = [
    "CategoryResult",
    "evaluate_resource_pattern",
    "evaluate_network_pattern",
    "evaluate_system_pattern",
]
