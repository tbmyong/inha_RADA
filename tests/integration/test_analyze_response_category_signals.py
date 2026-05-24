"""/analyze 응답에 category_signals 키가 포함되는지 검증."""
from __future__ import annotations
import pytest

from .fixtures import normal_metrics

pytestmark = pytest.mark.integration


def test_normal_response_includes_category_signals(client):
    payload = normal_metrics(pc_id="pc-CS1", slot="class", idx=0)
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    assert "category_signals" in body
    cs = body["category_signals"]
    assert set(cs.keys()) >= {
        "resource_abnormal", "network_abnormal", "system_abnormal",
        "sustained_minutes", "triggered_patterns", "verdict_from_gating",
    }
    # NORMAL 상태에서 모든 카테고리는 False, triggered 는 비어있음
    assert cs["resource_abnormal"] is False
    assert cs["network_abnormal"] is False
    assert cs["system_abnormal"] is False
    assert cs["triggered_patterns"] == []
    assert cs["verdict_from_gating"] == "NORMAL"


def test_legacy_keys_preserved(client):
    """기존 응답 형식 호환 — overall_severity, scores.score_breakdown, alerts 등 보존."""
    payload = normal_metrics(pc_id="pc-CS2", slot="class", idx=0)
    r = client.post("/analyze", json=payload)
    body = r.json()
    assert "overall_severity" in body
    assert "verdict" in body
    assert "alerts" in body
    assert "signals_missing" in body
    assert "policy_version" in body
    scores = body["scores"]
    assert "score_breakdown" in scores
    breakdown = scores["score_breakdown"]
    # 9 키 형식 유지 (resource/network/process/episode/correlation/ml/retrieval/context_discount/final)
    for k in (
        "resource", "network", "process", "episode",
        "correlation", "ml", "retrieval", "context_discount", "final",
    ):
        assert k in breakdown, f"missing breakdown key: {k}"


def test_policy_version_v07(client):
    payload = normal_metrics(pc_id="pc-CS3", slot="class", idx=0)
    r = client.post("/analyze", json=payload)
    body = r.json()
    # P0-3: policy bump v0.6 → v0.7 (promotion_gating 도입).
    # P1-*: policy bump v0.7 → v0.8 (dos_detection + episode_dedupe 도입).
    assert (body["policy_version"].startswith("scoring-v0.7")
            or body["policy_version"].startswith("scoring-v0.8"))
