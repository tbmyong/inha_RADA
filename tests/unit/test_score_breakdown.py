"""scores.score_breakdown 8키 구조 — 1단계는 process/ml/final만 정확값."""
from collections import deque

from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest

EXPECTED_KEYS = {
    "resource", "network", "process", "episode",
    "correlation", "ml", "context_discount", "final",
}


def _metrics(**overrides):
    base = dict(
        pc_id="pc-sb", timestamp="2026-05-04T10:00:00",
        cpu_percent=20.0, memory_percent=40.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )
    base.update(overrides)
    return MetricsRequest(**base)


def test_score_breakdown_has_eight_keys():
    result = analyze_pattern(_metrics(), deque(), slot="class")
    sb = result["scores"]["score_breakdown"]
    assert EXPECTED_KEYS.issubset(set(sb.keys()))


def test_score_breakdown_final_matches_scores_final():
    result = analyze_pattern(_metrics(), deque(), slot="class")
    assert result["scores"]["score_breakdown"]["final"] == result["scores"]["final"]


def test_score_breakdown_process_and_ml_mapped():
    """process / ml 필드는 indicators에서 직접 매핑."""
    result = analyze_pattern(_metrics(), deque(), slot="class")
    sb = result["scores"]["score_breakdown"]
    assert sb["process"] == result["scores"]["process"]
    assert sb["ml"]      == result["scores"]["ml"]


def test_score_breakdown_stage3_keys_typed():
    """3단계: resource/network/episode/correlation은 int, context_discount는 ≤0 int."""
    result = analyze_pattern(_metrics(), deque(), slot="class")
    sb = result["scores"]["score_breakdown"]
    for k in ("resource", "network", "episode", "correlation"):
        assert isinstance(sb[k], int) and sb[k] >= 0
    assert isinstance(sb["context_discount"], int)
    assert sb["context_discount"] <= 0
