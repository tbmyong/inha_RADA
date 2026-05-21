"""카테고리 게이팅 단위 테스트."""
from __future__ import annotations

from ml_server.scorer.pattern_categories import CategoryResult
from ml_server.scorer import category_gating


def _state():
    return {
        "all_three_since": None,
        "any_two_since": None,
        "any_one_since": None,
        "last_cats_count": 0,
        "last_ts": 0.0,
    }


CFG = {"gating": {
    "mining_confirmed": {"categories_required": 3, "sustained_minutes": 180},
    "suspicious":       {"categories_required": 2, "sustained_minutes": 30},
    "observe":          {"categories_required": 1, "sustained_minutes": 5},
}}


def _abn(triggered=("X",)):
    return CategoryResult(abnormal=True, triggered_patterns=list(triggered))


def _ok():
    return CategoryResult(abnormal=False, triggered_patterns=[])


def test_normal_when_no_categories_abnormal():
    s = _state()
    r = category_gating.evaluate(_ok(), _ok(), _ok(), s, CFG, now=1000.0)
    assert r.verdict == "NORMAL"
    assert r.cats_count == 0


def test_one_category_not_yet_sustained_is_normal():
    s = _state()
    # First call sets any_one_since = now, sustained=0 → no verdict yet (under 5min)
    r = category_gating.evaluate(_abn(), _ok(), _ok(), s, CFG, now=1000.0)
    assert r.verdict == "NORMAL"
    assert r.cats_count == 1


def test_one_category_observe_after_5min():
    s = _state()
    category_gating.evaluate(_abn(), _ok(), _ok(), s, CFG, now=1000.0)
    r = category_gating.evaluate(_abn(), _ok(), _ok(), s, CFG, now=1000.0 + 6 * 60)
    assert r.verdict == "OBSERVE"


def test_two_categories_suspicious_after_30min():
    s = _state()
    category_gating.evaluate(_abn(), _abn(), _ok(), s, CFG, now=1000.0)
    r = category_gating.evaluate(_abn(), _abn(), _ok(), s, CFG, now=1000.0 + 31 * 60)
    assert r.verdict == "SUSPICIOUS"
    assert r.cats_count == 2


def test_three_categories_below_180min_is_suspicious():
    s = _state()
    category_gating.evaluate(_abn(), _abn(), _abn(), s, CFG, now=1000.0)
    r = category_gating.evaluate(_abn(), _abn(), _abn(), s, CFG, now=1000.0 + 60 * 60)
    # sustained = 60 < 180 → not HIGH_RISK; 60 >= 30 + cats>=2 → SUSPICIOUS
    assert r.verdict == "SUSPICIOUS"


def test_three_categories_above_180min_is_high_risk():
    s = _state()
    category_gating.evaluate(_abn(), _abn(), _abn(), s, CFG, now=1000.0)
    r = category_gating.evaluate(_abn(), _abn(), _abn(), s, CFG, now=1000.0 + 181 * 60)
    assert r.verdict == "HIGH_RISK"
    assert r.cats_count == 3
    assert r.detail.get("alert_type") == "MINING_CONFIRMED_BY_BEHAVIOR"


def test_sustained_resets_when_count_drops():
    s = _state()
    category_gating.evaluate(_abn(), _abn(), _abn(), s, CFG, now=1000.0)
    # Drop to 1 — should reset 2 and 3 since states.
    category_gating.evaluate(_abn(), _ok(), _ok(), s, CFG, now=2000.0)
    assert s["all_three_since"] is None
    assert s["any_two_since"] is None
    # Going back to 3 starts new "all_three_since"
    r = category_gating.evaluate(_abn(), _abn(), _abn(), s, CFG, now=3000.0)
    assert r.cats_count == 3
    assert s["all_three_since"] == 3000.0


def test_detail_includes_triggered_patterns():
    s = _state()
    r = category_gating.evaluate(
        _abn(["R1"]), _abn(["N2"]), _abn(["S1"]), s, CFG, now=1000.0)
    assert "R1" in r.detail["triggered_patterns"]
    assert "N2" in r.detail["triggered_patterns"]
    assert "S1" in r.detail["triggered_patterns"]
    assert r.detail["resource_abnormal"] is True
    assert r.detail["network_abnormal"] is True
    assert r.detail["system_abnormal"] is True
