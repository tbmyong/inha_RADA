"""응답 스키마/금지표현 회귀 테스트."""
from __future__ import annotations

import pytest

from .fixtures import seed_history, normal_metrics, anomaly_metrics

pytestmark = pytest.mark.integration


REQUIRED_TOP_KEYS = {
    "pc_id", "timestamp", "timetable_slot",
    "overall_severity", "verdict",
    "alerts", "scores", "signals",
    "history_size", "isolation_forest",
    "global_hw_degradation", "agent",
}

REQUIRED_IF_KEYS = {
    "if_score", "lof_score", "weighted_score",
    "is_anomaly", "if_anomaly", "lof_anomaly",
    "boxplot_flag", "sample_count", "lof_window_size",
    "contamination", "boxplot_filtered",
}

FORBIDDEN_PHRASES = ["확실시", "EDR", "오탐 제거"]

SCORE_BREAKDOWN_KEYS = {
    "resource", "network", "process", "episode",
    "correlation", "ml", "context_discount", "final",
}
VERDICT_VALS  = {"NORMAL", "OBSERVE", "SUSPICIOUS", "HIGH_RISK"}
SEVERITY_VALS = {"NORMAL", "LOW", "MEDIUM", "HIGH"}
HW_VALS       = {"NONE", "SUSPECTED", "CONFIRMED"}


def test_response_schema_required_keys(client):
    """학습 후 이상 입력 응답이 모든 필수 키를 포함."""
    seed_history(client, pc_id="pc-schema", slot="class", n=60)
    r = client.post("/analyze",
                    json=anomaly_metrics(pc_id="pc-schema", slot="class", idx=300))
    body = r.json()

    # 최상위 키
    missing = REQUIRED_TOP_KEYS - set(body.keys())
    assert not missing, f"missing top keys: {missing}"

    # isolation_forest 키 (학습 완료 시)
    iso = body["isolation_forest"]
    assert iso["available"] is True
    if_missing = REQUIRED_IF_KEYS - set(iso.keys())
    assert not if_missing, f"missing IF keys: {if_missing}"


def test_response_schema_insufficient_keys(client):
    """학습 미완료 시 isolation_forest 키 일부만 존재 (Spring 호환)."""
    r = client.post("/analyze",
                    json=normal_metrics(pc_id="pc-schema-empty",
                                        slot="class", idx=0))
    body = r.json()
    iso = body["isolation_forest"]
    assert iso["available"] is False
    # 미학습 시에도 sample_count / weighted_score / is_anomaly 키는 존재
    for k in ("sample_count", "weighted_score", "is_anomaly",
              "if_score", "lof_score"):
        assert k in iso, f"missing key on insufficient: {k}"


def test_score_breakdown_eight_keys(client):
    """scores.score_breakdown은 8개 키를 가진다."""
    seed_history(client, pc_id="pc-sb", slot="class", n=60)
    r = client.post("/analyze",
                    json=anomaly_metrics(pc_id="pc-sb", slot="class", idx=300))
    body = r.json()
    sb = body["scores"]["score_breakdown"]
    assert SCORE_BREAKDOWN_KEYS.issubset(set(sb.keys()))
    # final은 scores.final과 일치
    assert sb["final"] == body["scores"]["final"]


def test_verdict_and_severity_enums(client):
    """verdict ∈ 4단계, overall_severity ∈ 4단계."""
    seed_history(client, pc_id="pc-enum", slot="class", n=60)
    r = client.post("/analyze",
                    json=anomaly_metrics(pc_id="pc-enum", slot="class", idx=300))
    body = r.json()
    assert body["verdict"] in VERDICT_VALS
    assert body["overall_severity"] in SEVERITY_VALS
    if body["agent"]:
        assert body["agent"]["hw_degradation"] in HW_VALS


def test_forbidden_expressions(client):
    """alerts/agent.reason/agent.action 에 금지 표현 미포함."""
    seed_history(client, pc_id="pc-forbid", slot="class", n=60)
    r = client.post("/analyze",
                    json=anomaly_metrics(pc_id="pc-forbid", slot="class", idx=300))
    body = r.json()

    blobs = []
    for a in body["alerts"]:
        blobs.append(str(a.get("detail", "")))
        blobs.append(str(a.get("type", "")))
    if body["agent"]:
        blobs.append(str(body["agent"].get("reason", "")))
        blobs.append(str(body["agent"].get("action", "")))

    joined = " ".join(blobs)
    for bad in FORBIDDEN_PHRASES:
        assert bad not in joined, f"forbidden phrase '{bad}' in: {joined}"
