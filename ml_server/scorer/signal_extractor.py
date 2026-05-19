"""Layer 1 — 24개 원자 단위 신호 추출 (판단 없음).

네트워크 규칙 기반 신호 단독 + GPU/CPU/메모리/프로세스/스텔스 모순 신호 포함.
"""
import statistics
from typing import Dict, Any
from collections import deque

from ..config import (
    GAME_RENDER_PROCESSES, COMPILE_ENCODE_PROCESSES,
    MINING_PROCESSES, MINING_POOL_IPS, SUSPICIOUS_PATHS, WHITELIST_PROCESSES,
)
from ..model.requests import MetricsRequest
from ..policy import get_allowlist


def _effective_whitelist() -> set:
    """기존 WHITELIST_PROCESSES + YAML allowlist union (대소문자 무시)."""
    base = {p.lower() for p in WHITELIST_PROCESSES}
    try:
        al = get_allowlist()
        base |= {p.lower() for p in al.whitelist_processes}
    except Exception:
        pass
    return base


def extract_signals(metrics: MetricsRequest, history: deque, slot: str,
                    ml_weighted_score: float = 0.0) -> Dict[str, Any]:
    """원자 단위 24신호 + 컨텍스트 메타 반환.

    반환값에 signals(dict)와 메타(known_miners, mining_pool_ip_str, avg_inbound, dos_ratio)를
    함께 묶어 indicator/verdict 단계에서 재사용한다.
    """
    history_list = list(history)
    has_history  = len(history_list) >= 12
    whitelist_eff = _effective_whitelist()

    gpu = metrics.gpu

    running_procs = {p.get("name","").lower() for p in metrics.top_processes}
    is_gaming    = bool(running_procs & {g.lower() for g in GAME_RENDER_PROCESSES})
    is_compiling = bool(running_procs & {c.lower() for c in COMPILE_ENCODE_PROCESSES})

    # GPU 기초값
    gpu_pct    = gpu.load_percent      if gpu else 0.0
    vram_mb    = gpu.memory_used_mb    if gpu else 0.0
    vram_total = (gpu.memory_total_mb  if gpu else 0.0) or 8192.0
    tensor     = gpu.tensor_core_active if gpu else None
    power      = gpu.power_draw_w      if gpu else None
    sm         = gpu.sm_utilization    if gpu else None
    vram_ratio = vram_mb / vram_total
    gpu_active = gpu_pct >= 30.0

    gpu_stddev = vram_stddev = power_stddev = avg_power = avg_gpu_pct = None
    if has_history and gpu:
        gpu_vals = [h["gpu_percent"] for h in history_list if h.get("gpu_percent") is not None]
        if len(gpu_vals) >= 12:
            gpu_stddev  = statistics.stdev(gpu_vals)
            avg_gpu_pct = statistics.mean(gpu_vals)
        vram_vals = [h["gpu_vram_mb"] for h in history_list if h.get("gpu_vram_mb") is not None]
        if len(vram_vals) >= 12:
            vram_stddev = statistics.stdev(vram_vals)
        power_vals = [h["gpu_power_w"] for h in history_list if h.get("gpu_power_w")]
        if len(power_vals) >= 12:
            avg_power    = statistics.mean(power_vals)
            power_stddev = statistics.stdev(power_vals)

    cpu_stddev = avg_cpu = None
    if has_history:
        cpu_vals   = [h["cpu_percent"] for h in history_list]
        cpu_stddev = statistics.stdev(cpu_vals)
        avg_cpu    = statistics.mean(cpu_vals)

    avg_inbound = avg_outbound = avg_ext_count = 0.0
    outbound_stddev = None
    if has_history:
        avg_inbound  = statistics.mean([h["inbound_mb"]  for h in history_list])
        avg_outbound = statistics.mean([h["outbound_mb"] for h in history_list])
        avg_ext_count= statistics.mean([h["external_packet_count"] for h in history_list])
        ob_vals = [h["outbound_mb"] for h in history_list]
        if len(ob_vals) >= 2:
            outbound_stddev = statistics.stdev(ob_vals)

    # 네트워크 — 규칙 기반 (ML과 분리)
    mining_pool_hit = any(
        conn.get("ip","").startswith(prefix)
        for conn in metrics.external_connections
        for prefix in MINING_POOL_IPS
    )
    mining_pool_ip_str = next(
        (conn.get("ip","") for conn in metrics.external_connections
         if any(conn.get("ip","").startswith(p) for p in MINING_POOL_IPS)), ""
    )

    dos_ratio     = {"class": 30, "free": 15}.get(slot, 15)
    dos_spike_hit = avg_inbound > 0 and metrics.inbound_mb > avg_inbound * dos_ratio

    outbound_spike = (avg_outbound > 0.01
                      and metrics.outbound_mb > avg_outbound * 5
                      and metrics.outbound_mb > 1.0)

    # 프로세스
    known_miners = [p for p in metrics.top_processes
                    if p.get("name","").lower() in MINING_PROCESSES]
    temp_exec    = [p for p in metrics.top_processes
                    if any(sp in p.get("path","").lower() for sp in SUSPICIOUS_PATHS)
                    and p.get("name","").lower() not in whitelist_eff]

    # appdata 실행 (Roaming/Local AppData) — temp 와 별도 추적
    appdata_exec = [p for p in metrics.top_processes
                    if "\\appdata\\" in p.get("path","").lower()
                    and "\\appdata\\local\\temp\\" not in p.get("path","").lower()
                    and p.get("name","").lower() not in whitelist_eff]

    # exec_path_suspicious = temp 또는 appdata
    exec_path_suspicious = bool(temp_exec) or bool(appdata_exec)

    # unknown_process_active = top_processes 중 화이트리스트/마이너 외 cpu 50+ 프로세스
    unknown_process_active = any(
        (p.get("name","").lower() not in whitelist_eff
         and p.get("name","").lower() not in MINING_PROCESSES
         and float(p.get("cpu_percent", 0) or 0) >= 50.0)
        for p in metrics.top_processes
    )

    persistent_miner = has_history and len(known_miners) > 0 and any(
        sum(1 for h in history_list
            if any(p.get("name","").lower() == m.get("name","").lower()
                   for p in h.get("top_processes",[]))) >= 6
        for m in known_miners
    )

    # 스텔스 모순(Mismatch)
    stealth_mismatch_power = (avg_power    is not None
                               and avg_gpu_pct is not None
                               and avg_power    >= 80.0
                               and avg_gpu_pct  < 30.0)
    stealth_mismatch_vram  = (vram_ratio > 0.7
                               and gpu_pct < 20.0)

    # ── 파생 신호 (3단계 신규) ──
    # net_out_sustained: 평균 대비 outbound 가 1.5배 이상 유지 + 절대값 임계
    net_out_sustained = (avg_outbound > 0.005
                          and metrics.outbound_mb >= max(avg_outbound * 1.5, 0.5))

    # disk_write 와 동시 발생
    disk_write_net_out_sustained = (
        metrics.disk_write_mb >= 1.0 and net_out_sustained
    )

    # derived_features 활용
    df = getattr(metrics, "derived_features", None) or {}
    if not isinstance(df, dict):
        df = {}
    top_cpu_norm = float(df.get("top_process_cpu_sum_normalized") or 0.0)
    ext_truncated = bool(df.get("external_connection_count_truncated") or False)
    unique_remote_ip_count = int(df.get("unique_remote_ip_count") or 0)
    duplicate_connection_count = int(df.get("duplicate_connection_count") or 0)
    gpu_missing_reason = df.get("gpu_metrics_missing_reason")
    network_missing_reason = df.get("network_collection_missing_reason")
    process_missing_reason = df.get("process_collection_missing_reason")
    derived_missing_reasons = df.get("derived_missing_reasons") or {}

    # signals_missing: 수집 실패한 카테고리. 점수 0 으로 잠그는 게 아니라
    # "측정 불가" 임을 명시해 silent fail 을 방지한다.
    signals_missing: list = []
    if network_missing_reason:
        signals_missing.append("network")
    if process_missing_reason:
        signals_missing.append("process")
    if derived_missing_reasons:
        signals_missing.append("derived_features")

    # new_remote_ip_burst: unique ip 가 급증 (>=8 또는 duplicate 적고 unique 많음)
    new_remote_ip_burst = (
        unique_remote_ip_count >= 8 and duplicate_connection_count < unique_remote_ip_count
    )

    mining_process_or_pool = (len(known_miners) > 0) or mining_pool_hit

    # spike_count_1m: external_packet_count 의 1분(12건) 합 ≥ 60 일 때 trigger
    # 단독 신호로는 0점 (indicator_calculator 에서 처리)
    spike_count_1m = metrics.external_packet_count >= 8  # 기존 net_external_high 와 동치

    signals: Dict[str, Any] = {
        "is_gaming":        is_gaming,
        "is_compiling":     is_compiling,
        "gpu_active":       gpu_active,
        "gpu_high":         gpu_pct >= 70,
        "gpu_flat":         (gpu_stddev is not None
                             and gpu_stddev < 5.0
                             and gpu_active),
        "gpu_cpu_gap":      gpu_pct >= 70 and metrics.cpu_percent < 20,
        "vram_low":         vram_ratio < 0.3 and gpu_active,
        "vram_stable":      (vram_stddev is not None
                             and vram_stddev < 50
                             and gpu_active),
        "power_stable":     (power_stddev is not None
                             and power_stddev < 10.0
                             and gpu_active
                             and avg_power is not None
                             and avg_power >= 60.0),
        "tensor_inactive":  tensor is not None and tensor == 0 and gpu_active,
        "sm_high":          sm is not None and sm >= 70,
        "stealth_mismatch_power": stealth_mismatch_power,
        "stealth_mismatch_vram":  stealth_mismatch_vram,
        "cpu_high":         metrics.cpu_percent >= 80,
        "cpu_flat":         (cpu_stddev is not None
                             and cpu_stddev < 5.0
                             and metrics.cpu_percent >= 60),
        "mem_critical":     metrics.memory_percent >= 95,
        "mem_high":         metrics.memory_percent >= 85,
        "net_external_high": metrics.external_packet_count >= 8,
        "mining_pool_ip":    mining_pool_hit,
        "outbound_spike":    outbound_spike,
        "dos_spike":         dos_spike_hit,
        "known_miner":       len(known_miners) > 0,
        "temp_exec":         len(temp_exec) > 0,
        "appdata_exec":      len(appdata_exec) > 0,
        "exec_path_suspicious": exec_path_suspicious,
        "unknown_process_active": unknown_process_active,
        "persistent_miner":  persistent_miner,
        "persistent_ext":    avg_ext_count >= 8,
        "ml_anomaly":        ml_weighted_score < -0.1,
        # 3단계 신규
        "net_out_sustained": net_out_sustained,
        "disk_write_net_out_sustained": disk_write_net_out_sustained,
        "new_remote_ip_burst": new_remote_ip_burst,
        "mining_process_or_pool": mining_process_or_pool,
        "spike_count_1m":    spike_count_1m,
    }

    # 수집 실패한 카테고리의 신호는 0/False 대신 명시적으로 drop (False 로 잠금).
    # 점수 산정 시 missing signal 을 "실제 0" 으로 오인하지 않도록 함.
    if network_missing_reason:
        for k in (
            "net_external_high", "mining_pool_ip", "outbound_spike", "dos_spike",
            "persistent_ext", "net_out_sustained",
            "disk_write_net_out_sustained", "new_remote_ip_burst",
            "spike_count_1m",
        ):
            if k in signals:
                signals[k] = False
    if process_missing_reason:
        for k in (
            "known_miner", "temp_exec", "appdata_exec", "exec_path_suspicious",
            "unknown_process_active", "persistent_miner", "mining_process_or_pool",
        ):
            if k in signals:
                signals[k] = False

    return {
        "signals":            signals,
        "signals_missing":    signals_missing,
        "is_gaming":          is_gaming,
        "is_compiling":       is_compiling,
        "known_miners":       known_miners,
        "mining_pool_ip_str": mining_pool_ip_str,
        "avg_inbound":        avg_inbound,
        "dos_ratio":          dos_ratio,
        "ml_weighted_score":  ml_weighted_score,
        # derived features 노출 (indicator_calculator 에서 사용)
        "top_process_cpu_sum_normalized": top_cpu_norm,
        "external_connection_count_truncated": ext_truncated,
        "unique_remote_ip_count": unique_remote_ip_count,
        "duplicate_connection_count": duplicate_connection_count,
        "gpu_metrics_missing_reason": gpu_missing_reason,
    }
