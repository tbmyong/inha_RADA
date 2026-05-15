"""Retrieval evidence builder.

retrieved cases 요약 + peer mismatch 계산 + retrieval score 산출.
점수 범위: -2 <= retrieval_score <= 5
"""
from __future__ import annotations
from typing import Dict, List, Optional


_RETRIEVAL_SCORE_MIN = -2
_RETRIEVAL_SCORE_MAX = 5

# embedding 거리 임계 — 이 값보다 작으면 "정말 유사" 로 간주
_NEAR_DISTANCE = 50.0


def _empty_evidence() -> dict:
    return {
        "available": False,
        "retrieval_score": 0,
        "similar_normal_count": 0,
        "similar_observe_count": 0,
        "similar_suspicious_count": 0,
        "similar_high_risk_count": 0,
        "novelty": False,
        "peer_mismatch": False,
        "same_slot_peer_count": 0,
        "similar_peer_spike_count": 0,
        "top_k": [],
    }


def _peer_compare(current_segment: Optional[dict],
                  peer_latest: Optional[dict]) -> tuple[int, int, bool]:
    """returns (same_slot_peer_count, similar_peer_spike_count, peer_mismatch).

    peer_latest: {pc_id: latest_metric_dict, ...}
    같은 slot 의 다른 PC 들이 거의 idle 인데 본 PC 만 spike 면 mismatch.
    """
    if not current_segment or not peer_latest:
        return 0, 0, False
    my_pc = current_segment.get("pc_id")
    my_slot = current_segment.get("slot")
    snaps = current_segment.get("snapshots") or []
    if not snaps:
        return 0, 0, False
    last = snaps[-1] if isinstance(snaps[-1], dict) else {}
    my_cpu = float(last.get("cpu_percent") or 0.0)

    same_slot = 0
    spikes = 0
    for pid, info in peer_latest.items():
        if not isinstance(info, dict) or pid == my_pc:
            continue
        if info.get("slot") and info.get("slot") != my_slot:
            continue
        same_slot += 1
        try:
            cpu = float(info.get("cpu_percent") or 0.0)
        except (TypeError, ValueError):
            cpu = 0.0
        if cpu >= 70.0:
            spikes += 1

    mismatch = False
    if same_slot >= 3 and my_cpu >= 70.0 and spikes == 0:
        mismatch = True
    return same_slot, spikes, mismatch


def build_retrieval_evidence(
    current_segment: Optional[dict],
    retrieved_cases: List[dict],
    peer_latest: Optional[Dict[str, dict]] = None,
) -> dict:
    if current_segment is None:
        return _empty_evidence()

    cases = retrieved_cases or []
    counts = {"NORMAL": 0, "OBSERVE": 0, "SUSPICIOUS": 0, "HIGH_RISK": 0}
    for c in cases:
        v = c.get("verdict")
        if v in counts:
            counts[v] += 1

    novelty = len(cases) == 0

    same_slot, spikes, peer_mismatch = _peer_compare(current_segment, peer_latest)

    score = 0
    total = len(cases)
    # 유사 NORMAL 다수 — 단, 실제로 "가까운" 사례여야 한다 (distance 임계)
    near_normal = sum(
        1 for c in cases
        if c.get("verdict") == "NORMAL"
        and float(c.get("distance", 1e9) or 1e9) < _NEAR_DISTANCE
    )
    if total > 0 and near_normal >= max(2, (total + 1) // 2):
        score -= 2
    # 유사 HIGH_RISK 존재
    if counts["HIGH_RISK"] > 0:
        score += 3
    # 유사 SUSPICIOUS 존재 (HIGH_RISK 가산과 중복 가능)
    if counts["SUSPICIOUS"] > 0:
        score += 2
    # novelty
    if novelty:
        score += 1
    # peer mismatch
    if peer_mismatch:
        score += 2

    if score < _RETRIEVAL_SCORE_MIN:
        score = _RETRIEVAL_SCORE_MIN
    if score > _RETRIEVAL_SCORE_MAX:
        score = _RETRIEVAL_SCORE_MAX

    return {
        "available": True,
        "retrieval_score": int(score),
        "similar_normal_count":     counts["NORMAL"],
        "similar_observe_count":    counts["OBSERVE"],
        "similar_suspicious_count": counts["SUSPICIOUS"],
        "similar_high_risk_count":  counts["HIGH_RISK"],
        "novelty": bool(novelty),
        "peer_mismatch": bool(peer_mismatch),
        "same_slot_peer_count": int(same_slot),
        "similar_peer_spike_count": int(spikes),
        "top_k": cases,
    }
