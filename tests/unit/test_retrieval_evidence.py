"""Retrieval evidence builder 단위 테스트."""
from ml_server.retrieval.retrieval_evidence import build_retrieval_evidence


def _seg(pc_id="pc-1", slot="class", cpu=80.0):
    return {
        "segment_id": f"{pc_id}:{slot}:T",
        "pc_id": pc_id,
        "slot": slot,
        "start_ts": "T0",
        "end_ts": "T1",
        "snapshots": [{"cpu_percent": cpu}],
    }


def test_empty_segment_returns_unavailable():
    ev = build_retrieval_evidence(None, [], {})
    assert ev["available"] is False
    assert ev["retrieval_score"] == 0


def test_normal_majority_lowers_score():
    cases = [
        {"verdict": "NORMAL", "distance": 0.1},
        {"verdict": "NORMAL", "distance": 0.2},
        {"verdict": "NORMAL", "distance": 0.3},
    ]
    ev = build_retrieval_evidence(_seg(cpu=10.0), cases, {})
    # near-distance NORMAL 다수 → -2
    assert ev["retrieval_score"] <= -2
    assert ev["similar_normal_count"] == 3


def test_far_distance_normal_does_not_lower_score():
    # 멀리 떨어진 NORMAL 사례는 감점 트리거가 아니다 (이상 입력 → NORMAL 변경 방지)
    cases = [
        {"verdict": "NORMAL", "distance": 9999.0},
        {"verdict": "NORMAL", "distance": 9999.0},
        {"verdict": "NORMAL", "distance": 9999.0},
    ]
    ev = build_retrieval_evidence(_seg(cpu=10.0), cases, {})
    assert ev["retrieval_score"] > -2


def test_high_risk_raises_score():
    cases = [
        {"verdict": "HIGH_RISK", "distance": 0.1},
        {"verdict": "NORMAL", "distance": 0.5},
    ]
    ev = build_retrieval_evidence(_seg(cpu=10.0), cases, {})
    assert ev["retrieval_score"] >= 3


def test_novelty_when_no_cases():
    ev = build_retrieval_evidence(_seg(cpu=10.0), [], {})
    assert ev["novelty"] is True
    assert ev["retrieval_score"] >= 1


def test_peer_mismatch_raises_score():
    # 본인(pc-1) 제외한 5명 → same_slot_peer_count == 5
    peer = {f"pc-other-{i}": {"cpu_percent": 5.0, "slot": "class"} for i in range(5)}
    ev = build_retrieval_evidence(_seg(cpu=85.0), [], peer)
    assert ev["peer_mismatch"] is True
    assert ev["same_slot_peer_count"] == 5
    # novelty(+1) + peer_mismatch(+2)
    assert ev["retrieval_score"] >= 3


def test_score_clamped_range():
    cases = [{"verdict": "HIGH_RISK", "distance": 0.1}] * 5
    peer = {f"pc-{i}": {"cpu_percent": 5.0, "slot": "class"} for i in range(5)}
    ev = build_retrieval_evidence(_seg(cpu=85.0), cases, peer)
    assert -2 <= ev["retrieval_score"] <= 5
