"""DELETE /history/{pc_id} 엔드포인트 회귀/격리 검증.

clear_router 키 매칭 버그 회귀 — (pc_id, slot) 튜플 키 누락으로 score_history가
DELETE 후에도 남아있던 문제를 방지한다.
"""
from __future__ import annotations

import pytest

from ml_server.storage import (
    pc_history_store,
    score_history_store,
    model_store,
)

from .fixtures import seed_history, anomaly_metrics, normal_metrics

pytestmark = pytest.mark.integration


# ──────────────────────────────────────────
# 회귀 1: DELETE 후 동일 pc_id 재분석 시 score_history 0에서 시작
# ──────────────────────────────────────────
def test_score_history_cleared_after_delete(client):
    pc_id = "pc-clr-1"
    seed_history(client, pc_id=pc_id, slot="class", n=60)
    # 이상 1건 → score_history 누적
    client.post("/analyze", json=anomaly_metrics(pc_id=pc_id, slot="class", idx=300))
    assert (pc_id, "class") in score_history_store.pc_score_history
    assert len(score_history_store.pc_score_history[(pc_id, "class")]) > 0

    r = client.delete(f"/history/{pc_id}")
    assert r.status_code == 200
    assert "초기화" in r.json()["message"]

    # 모든 store에서 흔적 제거됐는지
    assert (pc_id, "class") not in score_history_store.pc_score_history
    assert (pc_id, "free") not in score_history_store.pc_score_history
    assert pc_id not in pc_history_store.pc_history
    assert pc_id not in pc_history_store.pc_train_history
    assert pc_id not in pc_history_store.all_pc_latest


# ──────────────────────────────────────────
# 회귀 2: rule_score_history도 누적 0
# ──────────────────────────────────────────
def test_rule_score_history_cleared_after_delete(client):
    pc_id = "pc-clr-2"
    seed_history(client, pc_id=pc_id, slot="class", n=60)
    client.post("/analyze", json=anomaly_metrics(pc_id=pc_id, slot="class", idx=300))
    # rule_score_history 도 적재됐는지 (하나 이상 슬롯)
    assert any(
        k[0] == pc_id for k in score_history_store.rule_score_history.keys()
    )

    r = client.delete(f"/history/{pc_id}")
    assert r.status_code == 200

    # rule_score_history 흔적 0
    assert not any(
        k[0] == pc_id for k in score_history_store.rule_score_history.keys()
    )


# ──────────────────────────────────────────
# 격리 1: pc_A 후 pc_B만 DELETE → pc_A 상태 유지
# ──────────────────────────────────────────
def test_delete_isolates_other_pcs(client):
    pc_a = "pc-clr-A"
    pc_b = "pc-clr-B"
    seed_history(client, pc_id=pc_a, slot="class", n=60)
    seed_history(client, pc_id=pc_b, slot="class", n=60)
    client.post("/analyze", json=anomaly_metrics(pc_id=pc_a, slot="class", idx=300))
    client.post("/analyze", json=anomaly_metrics(pc_id=pc_b, slot="class", idx=300))

    r = client.delete(f"/history/{pc_b}")
    assert r.status_code == 200

    # pc_A 상태 유지
    assert pc_a in pc_history_store.pc_history
    assert (pc_a, "class") in score_history_store.pc_score_history
    assert model_store.get_model(pc_a, "class") is not None
    # pc_B 흔적 0
    assert pc_b not in pc_history_store.pc_history
    assert (pc_b, "class") not in score_history_store.pc_score_history
    assert model_store.get_model(pc_b, "class") is None


# ──────────────────────────────────────────
# 격리 2: 동일 pc_id 두 슬롯 (class / free) 모두 정리
# ──────────────────────────────────────────
def test_delete_clears_both_slots(client):
    pc_id = "pc-clr-slots"
    # class 슬롯 학습 + 이상
    seed_history(client, pc_id=pc_id, slot="class", n=60)
    client.post("/analyze", json=anomaly_metrics(pc_id=pc_id, slot="class", idx=300))
    # free 슬롯 학습 + 이상
    seed_history(client, pc_id=pc_id, slot="free", n=60)
    client.post("/analyze", json=anomaly_metrics(pc_id=pc_id, slot="free", idx=300))

    assert (pc_id, "class") in score_history_store.pc_score_history
    assert (pc_id, "free") in score_history_store.pc_score_history

    r = client.delete(f"/history/{pc_id}")
    assert r.status_code == 200

    # 두 슬롯 모두 정리
    assert (pc_id, "class") not in score_history_store.pc_score_history
    assert (pc_id, "free") not in score_history_store.pc_score_history
    assert (pc_id, "class") not in score_history_store.rule_score_history
    assert (pc_id, "free") not in score_history_store.rule_score_history
    assert model_store.get_model(pc_id, "class") is None
    assert model_store.get_model(pc_id, "free") is None


# ──────────────────────────────────────────
# 모델 정리: 학습 후 DELETE → get_model None
# ──────────────────────────────────────────
def test_delete_clears_model(client):
    pc_id = "pc-clr-model"
    seed_history(client, pc_id=pc_id, slot="class", n=60)
    assert model_store.get_model(pc_id, "class") is not None

    r = client.delete(f"/history/{pc_id}")
    assert r.status_code == 200

    assert model_store.get_model(pc_id, "class") is None
    assert pc_id not in model_store.pc_models


# ──────────────────────────────────────────
# 응답 호환: message 필드, 상태 200
# ──────────────────────────────────────────
def test_response_schema_compat(client):
    pc_id = "pc-clr-resp"
    seed_history(client, pc_id=pc_id, slot="class", n=60)

    r = client.delete(f"/history/{pc_id}")
    assert r.status_code == 200
    body = r.json()
    assert "message" in body
    assert pc_id in body["message"]
    assert "초기화" in body["message"]


def test_response_when_absent(client):
    r = client.delete("/history/nonexistent-pc-xyz")
    assert r.status_code == 200
    body = r.json()
    assert "message" in body
    assert "없음" in body["message"]
