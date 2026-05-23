"""P0-3 promotion gating — docs/fp_field_analysis_v0.6.md §7-P0-3.

Field 측정에서 MEDIUM 의 74% (948/1314) 가 alert 1개로 진입했다. 단일 신호
승격을 막기 위해 signal_count + category_count gating 을 도입.

이 테스트는 verdict_classifier.apply_promotion_gating 의 결정 표를 검증한다.
analyze_pattern 전체를 통과시키는 회귀는 별도 (test_evidence_meta_response.py).
"""
from __future__ import annotations

import pytest

from ml_server.policy import reload_policies
from ml_server.scorer.verdict_classifier import apply_promotion_gating


@pytest.fixture(autouse=True)
def _reload_policy():
    reload_policies()
    yield


def _meta(*, signals=2, cats=1, fast_path=None):
    return {
        "active_signal_count": signals,
        "category_count":      cats,
        "active_categories":   ["resource"] * cats,
        "active_signals":      ["x"] * signals,
        "promotion_gated":     False,
        "promotion_reason":    "",
        "fast_path_match":     fast_path,
    }


# ── SUSPICIOUS (MEDIUM) tier ────────────────────────────────────────────
def test_medium_blocked_when_signal_count_below_3():
    v, m = apply_promotion_gating("SUSPICIOUS", _meta(signals=2, cats=2))
    assert v == "OBSERVE"
    assert m["promotion_gated"] is True
    assert "gating_blocked" in m["promotion_reason"]


def test_medium_blocked_when_category_count_below_2():
    v, m = apply_promotion_gating("SUSPICIOUS", _meta(signals=5, cats=1))
    assert v == "OBSERVE"
    assert m["promotion_gated"] is True


def test_medium_passes_when_signal_3_and_category_2():
    v, m = apply_promotion_gating("SUSPICIOUS", _meta(signals=3, cats=2))
    assert v == "SUSPICIOUS"
    assert m["promotion_gated"] is False
    assert m["promotion_reason"] == "gating_passed"


# ── HIGH_RISK (HIGH) tier ───────────────────────────────────────────────
def test_high_blocked_when_signal_count_below_4():
    # 3 신호 + 2 카테고리 → HIGH 불가 (medium 통과 → SUSPICIOUS 로 강등)
    v, m = apply_promotion_gating("HIGH_RISK", _meta(signals=3, cats=2))
    assert v == "SUSPICIOUS"
    assert m["promotion_gated"] is True


def test_high_passes_when_signal_4_and_category_2():
    v, m = apply_promotion_gating("HIGH_RISK", _meta(signals=4, cats=2))
    assert v == "HIGH_RISK"
    assert m["promotion_gated"] is False
    assert m["promotion_reason"] == "gating_passed"


def test_high_double_blocked_drops_to_observe():
    # 신호도 카테고리도 부족 → SUSPICIOUS 조건도 못 만족 → OBSERVE
    v, m = apply_promotion_gating("HIGH_RISK", _meta(signals=2, cats=1))
    assert v == "OBSERVE"
    assert m["promotion_gated"] is True


# ── Fast-path ───────────────────────────────────────────────────────────
def test_fastpath_mining_known_keeps_high_even_with_one_signal():
    v, m = apply_promotion_gating(
        "HIGH_RISK", _meta(signals=1, cats=1, fast_path="mining_known"))
    assert v == "HIGH_RISK"
    assert m["promotion_gated"] is False
    assert m["promotion_reason"] == "fast_path:mining_known"


def test_fastpath_confirmed_sustained_keeps_high():
    v, m = apply_promotion_gating(
        "HIGH_RISK", _meta(signals=1, cats=1, fast_path="confirmed_sustained"))
    assert v == "HIGH_RISK"
    assert m["promotion_reason"] == "fast_path:confirmed_sustained"


def test_fastpath_alerts_contain_confirmed_mining():
    v, m = apply_promotion_gating(
        "HIGH_RISK", _meta(signals=1, cats=1,
                            fast_path="alerts_contain_confirmed_mining"))
    assert v == "HIGH_RISK"
    assert "fast_path" in m["promotion_reason"]


def test_fastpath_overrides_gating_block():
    # gating 조건 미달이지만 fast-path 가 있으면 즉시 HIGH_RISK 유지
    v, m = apply_promotion_gating(
        "HIGH_RISK", _meta(signals=2, cats=1, fast_path="mining_known"))
    assert v == "HIGH_RISK"
    assert m["promotion_gated"] is False


# ── No-op tiers ─────────────────────────────────────────────────────────
def test_observe_not_gated():
    v, m = apply_promotion_gating("OBSERVE", _meta(signals=1, cats=1))
    assert v == "OBSERVE"
    assert m["promotion_reason"] == "gating_not_applicable"


def test_normal_not_gated():
    v, m = apply_promotion_gating("NORMAL", _meta(signals=0, cats=0))
    assert v == "NORMAL"
