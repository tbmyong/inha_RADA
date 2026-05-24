"""P1-4 — Retrieval positive score gating.

docs/fp_field_analysis_v0.6.md §7-P1-4.

retrieval_score ranges from -2 to +5. Before P1-4, a positive
retrieval_score (e.g. 3 for "similar HIGH_RISK exists" + 2 for "peer
mismatch" = 5) could combine with a weak single-category breakdown to
nudge final_score above OBSERVE/SUSPICIOUS thresholds purely on
similarity grounds. retrieval is supposed to be borderline confirmation,
not standalone evidence.

P1-4: retrieval positive score (≥ +3) is only added to adjusted_score
when at least 2 *other* breakdown categories are positive
(resource/network/process/episode/correlation/ml). Otherwise the score
contribution is zero and the response marks the gating in
``retrieval_evidence.retrieval_score_gated``. Negative retrieval (NORMAL
similars discount) is unaffected — it's still added.
"""
from __future__ import annotations

from collections import deque

import pytest

from ml_server.model.requests import MetricsRequest
from ml_server.policy import reload_policies
from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.storage import pc_history_store
from ml_server.storage.score_history_store import reset_rule_score_history


@pytest.fixture(autouse=True)
def _reset():
    reload_policies()
    pc_history_store.reset_all_state()
    reset_rule_score_history()
    yield
    pc_history_store.reset_all_state()
    reset_rule_score_history()


def _make_metrics(cpu_pct: float = 5.0, mem_pct: float = 30.0,
                  gpu_pct: float = 0.0) -> MetricsRequest:
    return MetricsRequest(
        pc_id="pc-p1-4",
        timestamp="2026-05-23T10:00:00+09:00",
        cpu_percent=cpu_pct,
        memory_percent=mem_pct,
        disk_read_mb=0.1, disk_write_mb=0.1,
        inbound_mb=0.1, outbound_mb=0.1,
        external_packet_count=0,
        gpu={"name": "x", "load_percent": gpu_pct, "memory_used_mb": 0,
             "memory_total_mb": 1, "memory_percent": 0},
        local_alerts=[],
    )


def test_positive_retrieval_no_other_categories_gated_out():
    """retrieval_score=5 with no other breakdown evidence → score 0."""
    m = _make_metrics()  # nothing else firing
    ev = {"available": True, "retrieval_score": 5}
    result = analyze_pattern(m, deque(), slot="free", retrieval_evidence=ev)
    breakdown = result["scores"]["score_breakdown"]
    # retrieval shown in breakdown for audit, but the effective score
    # added to adjusted is 0.
    assert breakdown["retrieval"] == 0
    assert ev["retrieval_score_gated"] is True
    assert ev["retrieval_score_effective"] == 0


def test_positive_retrieval_with_two_other_categories_passes():
    """retrieval_score=5 with mem_high + cpu_high (resource cat) is still
    a single category. Need two; supply high cpu (resource) + ML cap (ml)."""
    m = _make_metrics(cpu_pct=92.0, mem_pct=92.0)
    ev = {"available": True, "retrieval_score": 5}
    # ml_weighted_score < -0.1 → ml category positive → 2 categories
    result = analyze_pattern(m, deque(), slot="free",
                             ml_weighted_score=-0.5,
                             retrieval_evidence=ev)
    breakdown = result["scores"]["score_breakdown"]
    assert breakdown["retrieval"] == 5
    assert ev["retrieval_score_gated"] is False
    assert ev["retrieval_score_effective"] == 5


def test_negative_retrieval_always_applied():
    """Negative retrieval (NORMAL discount) is not gated — still applied."""
    m = _make_metrics()
    ev = {"available": True, "retrieval_score": -2}
    result = analyze_pattern(m, deque(), slot="free", retrieval_evidence=ev)
    breakdown = result["scores"]["score_breakdown"]
    # Negative scores pass through.
    assert breakdown["retrieval"] == -2
    assert ev["retrieval_score_gated"] is False


def test_low_positive_retrieval_below_three_not_gated():
    """retrieval_score below the +3 floor is not subject to gating; it
    passes unchanged regardless of other-category count (so the threshold
    is exclusive)."""
    m = _make_metrics()
    ev = {"available": True, "retrieval_score": 2}
    result = analyze_pattern(m, deque(), slot="free", retrieval_evidence=ev)
    breakdown = result["scores"]["score_breakdown"]
    assert breakdown["retrieval"] == 2
    assert ev["retrieval_score_gated"] is False


def test_retrieval_unavailable_yields_zero_and_no_gating_marker():
    """When retrieval block is missing 'available' is False, no score."""
    m = _make_metrics()
    result = analyze_pattern(m, deque(), slot="free", retrieval_evidence=None)
    assert result["scores"]["score_breakdown"]["retrieval"] == 0
