"""IF/LOF ml 기여 상한(cap=5) + rule/correlation 0이면 ml -= 2."""
from ml_server.scorer.indicator_calculator import calculate_indicators, ML_SCORE_CAP


def _signals_zero_rule():
    """모든 신호 False (rule/correlation 모두 0)."""
    return {
        "is_gaming": False, "is_compiling": False,
        "gpu_active": False, "gpu_high": False, "gpu_flat": False, "gpu_cpu_gap": False,
        "vram_low": False, "vram_stable": False, "power_stable": False,
        "tensor_inactive": False, "sm_high": False,
        "stealth_mismatch_power": False, "stealth_mismatch_vram": False,
        "cpu_high": False, "cpu_flat": False,
        "mem_critical": False, "mem_high": False,
        "net_external_high": False, "mining_pool_ip": False,
        "outbound_spike": False, "dos_spike": False,
        "known_miner": False, "temp_exec": False, "appdata_exec": False,
        "exec_path_suspicious": False, "unknown_process_active": False,
        "persistent_miner": False, "persistent_ext": False,
        "ml_anomaly": True,  # ML만 True
        "net_out_sustained": False,
        "disk_write_net_out_sustained": False,
        "new_remote_ip_burst": False,
        "mining_process_or_pool": False,
        "spike_count_1m": False,
    }


def test_ml_score_capped_at_5_with_strong_signal():
    sig = _signals_zero_rule()
    # ml_weighted_score=-10 → 정상값이면 50; cap 적용
    out = calculate_indicators(sig, slot="class", ml_weighted_score=-10.0)
    # cap=5, 다른 rule/corr 0 → ml -= 2 → 3
    assert out["ml"] <= ML_SCORE_CAP
    assert out["ml"] == ML_SCORE_CAP - 2


def test_ml_no_penalty_when_rule_present():
    sig = _signals_zero_rule()
    sig["cpu_high"] = True  # rule 카테고리 발생
    out = calculate_indicators(sig, slot="class", ml_weighted_score=-10.0)
    assert out["ml"] == ML_SCORE_CAP  # cap 적용만, -2 패널티 없음
