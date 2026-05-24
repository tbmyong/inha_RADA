"""P2 — backdoor scoring demotion + alert type removal.

docs/fp_field_analysis_post_p1.md §10.

Post-P0/P1 measurement showed 53/54 (98%) remaining persisted rows
were `SUSPICIOUS_BACKDOOR`, all originating from normal dev/streaming
activity (Chrome %APPDATA%, OneDrive sync, Discord, game launchers).
With the data RADA currently collects (network statistics + process
name/path) the existing backdoor signature cannot tell those apart
from a real attack — it conflates ordinary network persistence with
the actual attack surface. Stronger evidence (cmdline / digital
signature / per-PID network mapping) would be required to revisit,
but that's out of current scope.

This PR
- forces backdoor_score = 0 in indicator_calculator
- removes BACKDOOR from the top_cat candidate set in
  build_alerts → no SUSPICIOUS_BACKDOOR alert type ever produced
- leaves the raw signals (persistent_ext, net_external_high)
  reachable via evidence_meta.active_signals

The schema-level `scores.backdoor` field is preserved for backward
compatibility but is always 0.
"""
from __future__ import annotations

from collections import defaultdict

import pytest

from ml_server.scorer.indicator_calculator import calculate_indicators


def _make_signals(**overrides):
    """All signals default to False (defaultdict so any key access works).
    Override specific ones via kwargs."""
    sigs = defaultdict(lambda: False)
    for k, v in overrides.items():
        sigs[k] = v
    return sigs


def test_backdoor_score_is_zero_with_persistent_ext_alone():
    """이전 P0/P1 측정에서 53/54 의 FP 원인 — persistent_ext 만으로 backdoor=3
    부여되던 패턴. 이제 0."""
    indicators = calculate_indicators(
        _make_signals(persistent_ext=True),
        slot="free", ml_weighted_score=0.0,
    )
    assert indicators["backdoor"] == 0


def test_backdoor_score_is_zero_with_net_external_high():
    """net_external_high 가 더해져도 0."""
    indicators = calculate_indicators(
        _make_signals(persistent_ext=True, net_external_high=True),
        slot="free", ml_weighted_score=0.0,
    )
    assert indicators["backdoor"] == 0


def test_backdoor_score_is_zero_in_class_slot_too():
    """슬롯 무관하게 0. 이전엔 free slot 한정이었지만 이제 어디서도 0."""
    indicators = calculate_indicators(
        _make_signals(persistent_ext=True, net_external_high=True),
        slot="class", ml_weighted_score=0.0,
    )
    assert indicators["backdoor"] == 0


def test_indicators_field_still_present_for_backward_compat():
    """scores.backdoor JSON 필드는 유지 (호환). 값만 항상 0."""
    indicators = calculate_indicators(_make_signals(), slot="free",
                                       ml_weighted_score=0.0)
    assert "backdoor" in indicators
    assert indicators["backdoor"] == 0


def test_raw_signals_still_in_results_path():
    """persistent_ext, net_external_high 는 signal_extractor 가 그대로 출력
    → evidence_meta.active_signals 로 노출됨. 본 테스트는 indicator_calculator
    가 호출 후에도 두 raw signal 의 boolean 값이 그대로 유지되는지 검증."""
    sigs = _make_signals(persistent_ext=True, net_external_high=True)
    calculate_indicators(sigs, slot="free", ml_weighted_score=0.0)
    assert sigs["persistent_ext"] is True
    assert sigs["net_external_high"] is True


def test_no_backdoor_alert_type_in_build_alerts():
    """build_alerts 의 top_cat 후보에서 BACKDOOR 제거됨. P2 본질."""
    from ml_server.scorer import verdict_classifier
    import inspect
    src = inspect.getsource(verdict_classifier.build_alerts)
    # top_cat 매칭 리스트에서 BACKDOOR 빠졌음
    assert '("BACKDOOR",   indicators["backdoor"])' not in src
    assert '("BACKDOOR"' not in src
