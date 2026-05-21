"""카테고리 패턴 evaluator 단위 테스트."""
from __future__ import annotations
from typing import List

import pytest

from ml_server.scorer import pattern_categories as pc


def _build_window(n: int, **fields) -> List[dict]:
    """field 값을 모두 동일하게 세팅한 1분 aggregate 엔트리 n 개."""
    base = {
        "ts": 0.0,
        "cpu_mean": 0.0, "cpu_std": 0.0, "cpu_max": 0.0,
        "gpu_mean": 0.0, "gpu_std": 0.0, "gpu_max": 0.0,
        "mem_used_gb_mean": 8.0,
        "disk_io_mb_mean": 0.0,
        "outbound_mb_mean": 0.0, "outbound_mb_std": 0.0,
        "inbound_mb_mean": 0.0,
        "vram_used_mb_mean": 0.0,
        "gpu_power_w_mean": 0.0, "gpu_power_w_std": 0.0,
        "user_idle_ms_max": 0.0,
        "external_endpoints": set(),
        "samples": 12,
    }
    base.update(fields)
    return [dict(base) for _ in range(n)]


@pytest.fixture
def cfg():
    return {
        "resource": {
            "R1_cpu_flat_sustained": {"threshold": {"cpu_pct": 90, "std": 5, "window_min": 30}},
            "R2_gpu_flat_sustained": {"threshold": {"gpu_pct": 90, "std": 5, "window_min": 30}},
            "R3_cpu_gpu_both_high":  {"threshold": {"cpu_pct": 90, "gpu_pct": 90, "window_min": 30}},
            "R4_gpu_only_asymmetric":{"threshold": {"gpu_pct": 90, "cpu_pct_max": 15, "window_min": 30}},
            "R5_power_flatline":     {"threshold": {"power_std_w": 5, "power_pct_of_tdp": 70, "tdp_w": 200, "window_min": 30}},
            "R6_sm_no_tensor":       {"enabled": False, "threshold": {}},
            "R7_vram_low_compute_high": {"threshold": {"vram_used_mb_max": 1024, "gpu_pct": 90, "window_min": 30}},
            "R8_mem_idle_compute_high": {"threshold": {"mem_used_gb_max": 4, "gpu_pct": 90, "window_min": 30}},
            "R9_single_core_full":   {"enabled": False, "threshold": {}},
        },
        "network": {
            "N1_stratum_periodicity": {"enabled": False, "threshold": {}},
            "N2_external_ip_persistent": {"threshold": {"same_endpoint_minutes": 30}},
            "N4_internal_zero_external_high": {"threshold": {"internal_kb": 0, "external_mb_min": 1, "window_min": 30}},
            "N5_outbound_low_cv": {"threshold": {"cv_max": 0.3, "window_min": 30}},
            "N6_dns_burst_during_idle": {"enabled": False, "threshold": {}},
        },
        "system": {
            "S1_user_idle_high_load": {"threshold": {"user_idle_min": 30, "cpu_or_gpu_pct": 90, "window_min": 30}},
            "S2_locked_high_load":    {"enabled": False, "threshold": {}},
            "S3_high_load_disk_idle": {"threshold": {"cpu_or_gpu_pct": 90, "disk_mb_per_s_max": 1, "window_min": 30}},
            "S4_high_load_mem_idle":  {"threshold": {"cpu_or_gpu_pct": 90, "mem_used_gb_max": 4, "window_min": 30}},
            "S5_process_recreation":  {"enabled": False, "threshold": {}},
        },
    }


# ── Resource ──
def test_R1_cpu_flat_positive(cfg):
    win = _build_window(30, cpu_mean=95.0, cpu_std=2.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert r.abnormal
    assert "R1" in r.triggered_patterns


def test_R1_cpu_high_but_volatile_negative(cfg):
    win = _build_window(30, cpu_mean=95.0, cpu_std=10.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R1" not in r.triggered_patterns


def test_R2_gpu_flat_positive(cfg):
    win = _build_window(30, gpu_mean=95.0, gpu_std=2.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R2" in r.triggered_patterns


def test_R3_both_high(cfg):
    win = _build_window(30, cpu_mean=92.0, gpu_mean=95.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R3" in r.triggered_patterns


def test_R4_gpu_only_asymmetric(cfg):
    win = _build_window(30, cpu_mean=10.0, gpu_mean=95.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R4" in r.triggered_patterns


def test_R5_power_flatline(cfg):
    # tdp 200 * 0.7 = 140W mean, std < 5
    win = _build_window(30, gpu_power_w_mean=150.0, gpu_power_w_std=2.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R5" in r.triggered_patterns


def test_R7_vram_low_compute_high(cfg):
    win = _build_window(30, gpu_mean=95.0, vram_used_mb_mean=500.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R7" in r.triggered_patterns


def test_R8_mem_idle_compute_high(cfg):
    win = _build_window(30, gpu_mean=95.0, mem_used_gb_mean=2.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R8" in r.triggered_patterns


def test_resource_no_trigger_short_window(cfg):
    win = _build_window(10, cpu_mean=95.0, cpu_std=1.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert not r.abnormal


def test_R6_R9_stubbed(cfg):
    # enable in cfg but evaluator should not trigger (stub)
    cfg["resource"]["R6_sm_no_tensor"] = {"threshold": {}}
    cfg["resource"]["R9_single_core_full"] = {"threshold": {}}
    win = _build_window(30, cpu_mean=99.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R6" not in r.triggered_patterns
    assert "R9" not in r.triggered_patterns


# ── Network ──
def test_N2_persistent_endpoint(cfg):
    eps = {"1.2.3.4"}
    win = _build_window(30, external_endpoints=eps)
    r = pc.evaluate_network_pattern(win, {}, cfg)
    assert "N2" in r.triggered_patterns


def test_N2_negative_changing_endpoints(cfg):
    win = []
    for i in range(30):
        e = _build_window(1, external_endpoints={f"10.0.0.{i}"})[0]
        win.append(e)
    r = pc.evaluate_network_pattern(win, {}, cfg)
    assert "N2" not in r.triggered_patterns


def test_N4_internal_zero_external_high(cfg):
    win = _build_window(30, outbound_mb_mean=0.5, inbound_mb_mean=0.0)
    r = pc.evaluate_network_pattern(win, {}, cfg)
    assert "N4" in r.triggered_patterns


def test_N5_outbound_low_cv(cfg):
    win = _build_window(30, outbound_mb_mean=0.5, outbound_mb_std=0.05)
    r = pc.evaluate_network_pattern(win, {}, cfg)
    assert "N5" in r.triggered_patterns


def test_N5_high_cv_negative(cfg):
    win = _build_window(30, outbound_mb_mean=0.5, outbound_mb_std=0.3)
    r = pc.evaluate_network_pattern(win, {}, cfg)
    assert "N5" not in r.triggered_patterns


# ── System ──
def test_S1_user_idle_high_load(cfg):
    win = _build_window(30, cpu_mean=95.0, user_idle_ms_max=30 * 60 * 1000)
    r = pc.evaluate_system_pattern(win, {}, cfg)
    assert "S1" in r.triggered_patterns


def test_S1_negative_short_idle(cfg):
    win = _build_window(30, cpu_mean=95.0, user_idle_ms_max=1000)
    r = pc.evaluate_system_pattern(win, {}, cfg)
    assert "S1" not in r.triggered_patterns


def test_S3_high_load_disk_idle(cfg):
    win = _build_window(30, gpu_mean=95.0, disk_io_mb_mean=0.1)
    r = pc.evaluate_system_pattern(win, {}, cfg)
    assert "S3" in r.triggered_patterns


def test_S4_high_load_mem_idle(cfg):
    win = _build_window(30, gpu_mean=95.0, mem_used_gb_mean=2.0)
    r = pc.evaluate_system_pattern(win, {}, cfg)
    assert "S4" in r.triggered_patterns


def test_S2_S5_stubbed(cfg):
    cfg["system"]["S2_locked_high_load"] = {"threshold": {}}
    cfg["system"]["S5_process_recreation"] = {"threshold": {}}
    win = _build_window(30, gpu_mean=99.0)
    r = pc.evaluate_system_pattern(win, {}, cfg)
    assert "S2" not in r.triggered_patterns
    assert "S5" not in r.triggered_patterns


def test_evaluator_empty_window(cfg):
    r1 = pc.evaluate_resource_pattern([], {}, cfg)
    r2 = pc.evaluate_network_pattern([], {}, cfg)
    r3 = pc.evaluate_system_pattern([], {}, cfg)
    assert not r1.abnormal and not r2.abnormal and not r3.abnormal


def test_disabled_pattern_no_trigger(cfg):
    cfg["resource"]["R1_cpu_flat_sustained"]["enabled"] = False
    win = _build_window(30, cpu_mean=99.0, cpu_std=1.0)
    r = pc.evaluate_resource_pattern(win, {}, cfg)
    assert "R1" not in r.triggered_patterns
