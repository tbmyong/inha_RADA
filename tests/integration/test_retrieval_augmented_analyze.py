"""Retrieval-augmented /analyze 통합 테스트."""
import pytest

from .fixtures import seed_history, normal_metrics, anomaly_metrics

pytestmark = pytest.mark.integration


def test_analyze_response_has_retrieval_evidence_key(client):
    """충분한 history 가 쌓이면 retrieval_evidence 가 응답에 포함."""
    seed_history(client, pc_id="pc-retr", slot="class", n=60)
    r = client.post("/analyze",
                    json=anomaly_metrics(pc_id="pc-retr", slot="class", idx=300))
    body = r.json()
    assert "retrieval_evidence" in body
    ev = body["retrieval_evidence"]
    assert ev is not None
    assert "retrieval_score" in ev
    assert "top_k" in ev


def test_score_breakdown_has_retrieval_key(client):
    seed_history(client, pc_id="pc-rb", slot="class", n=60)
    r = client.post("/analyze",
                    json=anomaly_metrics(pc_id="pc-rb", slot="class", idx=300))
    sb = r.json()["scores"]["score_breakdown"]
    assert "retrieval" in sb
    assert isinstance(sb["retrieval"], int)


def test_insufficient_history_no_evidence_but_endpoint_works(client):
    """초기엔 segment 미생성 — retrieval_evidence 가 None 이어도 응답 정상."""
    r = client.post("/analyze",
                    json=normal_metrics(pc_id="pc-init", slot="class", idx=0))
    assert r.status_code == 200
    body = r.json()
    assert "retrieval_evidence" in body
    # segment 못 만든 시점이면 None
    if body["retrieval_evidence"] is not None:
        assert body["retrieval_evidence"].get("available") in (True, False)


def test_clear_history_clears_retrieval_segments(client):
    seed_history(client, pc_id="pc-clr", slot="class", n=60)
    client.post("/analyze",
                json=anomaly_metrics(pc_id="pc-clr", slot="class", idx=300))
    from ml_server.retrieval import segment_history_by_slot
    before = sum(1 for s in segment_history_by_slot["class"] if s["pc_id"] == "pc-clr")
    assert before >= 1
    client.delete("/history/pc-clr")
    after = sum(1 for s in segment_history_by_slot["class"] if s["pc_id"] == "pc-clr")
    assert after == 0
