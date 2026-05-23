"""P0-3 evidence_meta 응답 구조 검증.

docs/fp_field_analysis_v0.6.md §7-P0-3:
응답 top-level 에 `evidence_meta` 추가:
  - active_signal_count / category_count / active_categories / active_signals
  - promotion_gated / promotion_reason / fast_path_match
"""
from __future__ import annotations

from collections import deque

import pytest

from ml_server.model.requests import MetricsRequest
from ml_server.policy import reload_policies
from ml_server.scorer.verdict_classifier import analyze_pattern


_REQUIRED_KEYS = {
    "active_signal_count", "category_count",
    "active_categories", "active_signals",
    "promotion_gated", "promotion_reason", "fast_path_match",
}


@pytest.fixture(autouse=True)
def _reload_policy():
    reload_policies()
    yield


def _make(cpu=5.0, mem=30.0, gpu_pct=0.0, miners=False, top=None,
          local_alerts=None, ext_conn=None, inbound=0.1, outbound=0.1):
    procs = list(top or [])
    if miners:
        procs.append({"name": "xmrig", "cpu_percent": 90.0, "path": "/tmp/xmrig"})
    return MetricsRequest(
        pc_id="ev-meta-pc",
        timestamp="2026-05-23T10:00:00+09:00",
        cpu_percent=cpu,
        memory_percent=mem,
        disk_read_mb=0.0,
        disk_write_mb=0.0,
        inbound_mb=inbound,
        outbound_mb=outbound,
        external_packet_count=0,
        external_connections=list(ext_conn or []),
        top_processes=procs,
        gpu={
            "name": "test", "load_percent": gpu_pct,
            "memory_used_mb": 0.0, "memory_total_mb": 8192.0,
            "memory_percent": 0.0,
        },
        local_alerts=list(local_alerts or []),
    )


def test_normal_response_has_evidence_meta_with_all_keys():
    """정상 케이스 — evidence_meta 가 모든 필수 키 포함. count 0."""
    m = _make()
    r = analyze_pattern(m, deque(), slot="free")
    em = r["evidence_meta"]
    assert set(em.keys()) >= _REQUIRED_KEYS
    assert em["active_signal_count"] == 0
    assert em["category_count"] == 0
    assert em["active_categories"] == []
    assert em["active_signals"] == []
    assert em["fast_path_match"] is None


def test_fast_path_mining_known_when_xmrig_running():
    """xmrig 발견 → process indicator 10 → fast_path_match=mining_known.

    classify_verdict 는 final_score 만 보지만, indicators[process]=10 이
    fast-path 식별의 신호. CONFIRMED_MINING alert 도 동반 발생.
    """
    m = _make(miners=True)
    r = analyze_pattern(m, deque(), slot="free")
    em = r["evidence_meta"]
    # mining_known 우선 (process_score>=10 직접 확인)
    assert em["fast_path_match"] == "mining_known"
    assert em["promotion_reason"].startswith("fast_path:")
    assert em["promotion_gated"] is False
    # CONFIRMED_MINING alert 동반 — fast-path 식별 보강
    alert_types = [a.get("type") for a in r["alerts"]]
    assert "CONFIRMED_MINING" in alert_types


def test_active_signals_includes_mem_and_cpu_when_high():
    """CPU+MEM high 동시 → active_signals 에 cpu_high / mem_high 포함,
    resource 카테고리 활성."""
    m = _make(cpu=90.0, mem=90.0)
    r = analyze_pattern(m, deque(), slot="free")
    em = r["evidence_meta"]
    sigs = set(em["active_signals"])
    assert "cpu_high" in sigs
    assert "mem_high" in sigs
    assert "resource" in em["active_categories"]


def test_gating_disabled_emits_reason_when_policy_off(monkeypatch):
    """promotion_gating.enabled=false → promotion_reason=gating_disabled."""
    from ml_server.policy import loader as _loader

    pol = _loader.load_scoring_policy()
    pg = pol.promotion_gating
    disabled = _loader.PromotionGating(
        enabled=False,
        medium_min_signal_count=pg.medium_min_signal_count,
        medium_min_category_count=pg.medium_min_category_count,
        high_min_signal_count=pg.high_min_signal_count,
        high_min_category_count=pg.high_min_category_count,
        fast_path=pg.fast_path,
    )
    new_policy = _loader.ScoringPolicy(
        version=pol.version,
        thresholds=pol.thresholds,
        limits=pol.limits,
        scores=pol.scores,
        context_discounts=pol.context_discounts,
        category_patterns=pol.category_patterns,
        gating=pol.gating,
        promotion_gating=disabled,
    )
    monkeypatch.setattr(_loader, "_scoring_policy_cache", new_policy)

    m = _make()
    r = analyze_pattern(m, deque(), slot="free")
    assert r["evidence_meta"]["promotion_reason"] == "gating_disabled"


def test_evidence_meta_present_even_for_normal_verdict():
    """verdict=NORMAL 인 케이스에도 evidence_meta 가 반드시 존재."""
    m = _make()
    r = analyze_pattern(m, deque(), slot="free")
    assert r["verdict"] == "NORMAL"
    assert "evidence_meta" in r
    assert r["evidence_meta"]["fast_path_match"] is None
