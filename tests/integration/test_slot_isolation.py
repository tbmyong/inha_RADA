"""슬롯별 모델 격리 — class에서 학습한 모델이 free 슬롯 요청에 적용되지 않음."""
from __future__ import annotations

import pytest

from ml_server.storage import model_store

from .fixtures import seed_history, normal_metrics

pytestmark = pytest.mark.integration


def test_slot_isolation_class_vs_free(client):
    pc_id = "pc-SLOT"

    # class 슬롯 학습
    seed_history(client, pc_id=pc_id, slot="class", n=60)

    # class 모델만 존재
    assert model_store.get_model(pc_id, "class") is not None
    assert model_store.get_model(pc_id, "free") is None

    # free 슬롯 1건 요청 → 학습 데이터 부족 → 모델 미사용
    r = client.post("/analyze",
                    json=normal_metrics(pc_id=pc_id, slot="free", idx=0))
    assert r.status_code == 200
    body = r.json()
    assert body["timetable_slot"] == "free"
    iso = body["isolation_forest"]
    assert iso["available"] is False
    # sample_count 분리: free 슬롯은 1건만
    # (모델 미보유 → predict 응답 sample_count=None, 학습 데이터 길이는 별도)
    assert iso["sample_count"] is None

    # 여전히 free 모델은 학습되지 않음
    assert model_store.get_model(pc_id, "free") is None
    # class 모델은 그대로
    class_model = model_store.get_model(pc_id, "class")
    assert class_model is not None
    assert class_model["sample_count"] >= 60
