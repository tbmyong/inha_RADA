"""Layer 2 — 신호 → 카테고리별 점수.

3단계: 기존 카테고리(gpu_mining/cpu_mining/stealth/exfil/process/dos/backdoor/mem/ml)
       호환 + 신규 8키 score_breakdown (resource/network/process/episode/correlation/
       ml/context_discount/final) 계산 보조.
"""
from typing import Dict, Any

from ..policy import get_scoring_policy


# 하위 호환: 일부 외부 import 가능성을 위해 모듈 레벨 상수도 보존
# (런타임 사용은 정책 파일을 통해 동적으로 결정)
ML_SCORE_CAP = 5  # default fallback; 실제 사용 시 policy.limits.ml_score_cap


def _ml_cap() -> int:
    try:
        return int(get_scoring_policy().limits.ml_score_cap)
    except Exception:
        return ML_SCORE_CAP


def calculate_indicators(signals: Dict[str, Any], slot: str,
                         ml_weighted_score: float = 0.0,
                         sig_pack: Dict[str, Any] = None) -> Dict[str, int]:
    sig_pack = sig_pack or {}
    ml_cap = _ml_cap()

    # ──────────────────────────────────────────
    # 기존 카테고리 (호환 유지)
    # ──────────────────────────────────────────
    gpu_mining_score = 0
    if signals["gpu_high"]:                          gpu_mining_score += 1
    if signals["gpu_flat"]:                          gpu_mining_score += 3
    if signals["gpu_cpu_gap"]:                       gpu_mining_score += 3
    if signals["net_external_high"]:                 gpu_mining_score += 1
    if signals["mining_pool_ip"]:                    gpu_mining_score += 5
    if signals["tensor_inactive"] and signals["vram_low"]: gpu_mining_score += 3
    if signals["is_gaming"]:                         gpu_mining_score -= 5

    cpu_mining_score = 0
    if signals["cpu_high"]:                          cpu_mining_score += 1
    if signals["cpu_flat"]:                          cpu_mining_score += 3
    if not signals["gpu_high"]:                      cpu_mining_score += 1
    if signals["mining_pool_ip"]:                    cpu_mining_score += 5
    if not signals["gpu_active"] and signals["cpu_high"] and signals["cpu_flat"]:
        cpu_mining_score += 2
    if signals["is_compiling"]:                      cpu_mining_score -= 5
    if signals["is_gaming"]:                         cpu_mining_score -= 3

    stealth_score = 0
    has_mismatch = signals["stealth_mismatch_power"] or signals["stealth_mismatch_vram"]
    if has_mismatch:
        if signals["stealth_mismatch_power"]:        stealth_score += 5
        if signals["stealth_mismatch_vram"]:         stealth_score += 5
        if signals["vram_stable"]:                   stealth_score += 1
        if signals["gpu_flat"]:                      stealth_score += 1
        if signals["power_stable"]:                  stealth_score += 1
        if signals["is_gaming"]:                     stealth_score -= 3
        if signals["is_compiling"]:                  stealth_score -= 2

    exfil_score = 0
    if signals["outbound_spike"]:                    exfil_score += 5
    if signals["net_external_high"]:                 exfil_score += 1

    process_score = 0
    if signals["known_miner"]:                       process_score += 10
    if signals["persistent_miner"]:                  process_score +=  3
    if signals["temp_exec"]:                         process_score +=  1

    dos_score = 0
    if signals["dos_spike"]:                         dos_score += 5

    # P2 (docs/fp_field_analysis_post_p1.md §10):
    # backdoor_score 는 0 으로 고정. 기존 (persistent_ext + net_external_high)
    # 만으론 정상 dev/스트리밍/클라우드 동기화 (Chrome, Discord, OneDrive, VS
    # Code, 게임 런처) 와 구분 불가 — Post-P0/P1 측정에서 잔여 FP 54건 중
    # 53건이 SUSPICIOUS_BACKDOOR 였고, 모두 정상 사용 패턴이었다.
    #
    # 진짜 backdoor 탐지는 Sysmon (process tree / cmdline / digital signature
    # / network connection PID 매핑 / registry persistence) 이 들어온 뒤
    # 재도입 예정. 그 전까지 backdoor verdict 승격은 비활성.
    #
    # raw signals (persistent_ext, net_external_high) 는 signal_extractor 에서
    # 그대로 출력 → evidence_meta.active_signals 에 노출 → 운영자가 직접 확인.
    backdoor_score = 0

    mem_score = 0
    if signals["mem_critical"]:                      mem_score += 1
    if signals["mem_high"] and not signals["cpu_high"]:
        mem_score += 1

    # ── ML 통합 + cap ──
    ml_score = 0
    if signals["ml_anomaly"]:
        ml_contribution = min(ml_cap, max(1, int(abs(ml_weighted_score) * 5)))
        ml_score += ml_contribution

    # ──────────────────────────────────────────
    # 신규 8키 breakdown 계산
    # ──────────────────────────────────────────
    top_cpu_norm = float(sig_pack.get("top_process_cpu_sum_normalized") or 0.0)
    ext_truncated = bool(sig_pack.get("external_connection_count_truncated") or False)
    unique_remote_ip = int(sig_pack.get("unique_remote_ip_count") or 0)
    gpu_missing = sig_pack.get("gpu_metrics_missing_reason")

    # resource = CPU/Mem/GPU/top_process_cpu_sum_normalized
    resource = 0
    if signals["cpu_high"]:           resource += 1
    if signals["cpu_flat"]:           resource += 1
    if signals["mem_high"]:           resource += 1
    if signals["mem_critical"]:       resource += 1
    if signals["gpu_high"] and not gpu_missing: resource += 1
    if top_cpu_norm >= 0.85:          resource += 2
    elif top_cpu_norm >= 0.6:         resource += 1

    # network
    # - spike_count_1m (=net_external_high) 단독은 0점
    # - 동반 신호가 있을 때만 가산
    network = 0
    if ext_truncated:
        network = 0  # visibility degraded
    else:
        companions = sum(1 for k in (
            "net_out_sustained", "unknown_process_active", "exec_path_suspicious",
            "disk_write_net_out_sustained", "new_remote_ip_burst",
            "mining_process_or_pool",
        ) if signals.get(k))

        # spike 단독 → 0
        if signals.get("spike_count_1m") and companions >= 1:
            network += 1
        if signals.get("net_out_sustained"):
            network += 2
        if signals.get("outbound_spike"):
            network += 2
        if unique_remote_ip >= 12:
            network += 2
        elif unique_remote_ip >= 6:
            network += 1
        if signals.get("new_remote_ip_burst"):
            network += 1

    # process (확정 증거)
    process_breakdown = 0
    if signals["known_miner"]:        process_breakdown += 10
    if signals["persistent_miner"]:   process_breakdown += 3
    if signals["temp_exec"]:          process_breakdown += 1
    if signals.get("appdata_exec"):   process_breakdown += 1

    # episode
    episode = 0
    if signals["dos_spike"]:          episode += 5
    if signals["persistent_ext"]:     episode += 2

    # correlation
    correlation = 0
    # cpu + disk + network 동시
    if signals["cpu_high"] and signals.get("net_out_sustained"):
        correlation += 2
    if signals.get("disk_write_net_out_sustained"):
        correlation += 5
    if signals.get("unknown_process_active") and signals.get("net_out_sustained"):
        correlation += 5
    if signals.get("appdata_exec") and signals.get("net_out_sustained"):
        correlation += 6
    if signals.get("mining_process_or_pool"):
        # process or pool: mining_process_or_pool 자체 신호
        if signals["known_miner"]:
            correlation += 10
        else:
            correlation += 8

    # ml after cap
    ml_breakdown = min(ml_cap, ml_score)
    # ml ≥ cap 이고 rule/correlation 합 0 → ml -= 2
    # 신규 8키 breakdown 의 rule/correlation 카테고리 합으로 판단
    rule_corr_sum = (
        resource + network + process_breakdown + episode + correlation
    )
    if ml_breakdown >= ml_cap and rule_corr_sum == 0:
        ml_breakdown = max(0, ml_breakdown - 2)

    return {
        # 기존 키 (호환)
        "gpu_mining": gpu_mining_score,
        "cpu_mining": cpu_mining_score,
        "stealth":    stealth_score,
        "exfil":      exfil_score,
        "process":    process_score,
        "dos":        dos_score,
        "backdoor":   backdoor_score,
        "mem":        mem_score,
        "ml":         ml_breakdown,  # cap 적용 후
        # 신규 8키 component (final/context_discount 는 verdict_classifier 에서 합산)
        "breakdown_resource":    resource,
        "breakdown_network":     network,
        "breakdown_process":     process_breakdown,
        "breakdown_episode":     episode,
        "breakdown_correlation": correlation,
        "breakdown_ml":          ml_breakdown,
    }
