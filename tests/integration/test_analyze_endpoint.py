"""시나리오 1~4: /analyze 엔드포인트 동작 검증."""
from __future__ import annotations

import pytest

from .fixtures import (
    seed_history, normal_metrics, anomaly_metrics, context_metrics,
)

pytestmark = pytest.mark.integration


# ──────────────────────────────────────────
# 시나리오 1: insufficient data → NORMAL
# ──────────────────────────────────────────
def test_insufficient_data_normal(client):
    payload = normal_metrics(pc_id="pc-S1", slot="class", idx=0)
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["overall_severity"] == "NORMAL"
    iso = body["isolation_forest"]
    # 학습 전: sample_count 는 None (모델 미보유)
    assert iso["available"] is False
    assert iso["sample_count"] is None
    # 패턴 분석은 정상 verdict
    assert body["verdict"] == "NORMAL"
    # agent 는 NORMAL 시 None
    assert body["agent"] is None


# ──────────────────────────────────────────
# 시나리오 2: 60건 seed 후 정상 입력 → NORMAL
# ──────────────────────────────────────────
def test_normal_after_training(client):
    seed_history(client, pc_id="pc-S2", slot="class", n=60)

    # seed 직후 정상 입력 1건
    payload = normal_metrics(pc_id="pc-S2", slot="class", idx=200)
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    iso = body["isolation_forest"]
    assert iso["available"] is True
    assert iso["sample_count"] >= 60
    # 학습 후 정상 분포 → NORMAL 또는 LOW (오탐 1건은 허용)
    assert body["overall_severity"] in {"NORMAL", "LOW"}


# ──────────────────────────────────────────
# 시나리오 3: 60건 seed 후 이상 입력 → 이상 verdict
# ──────────────────────────────────────────
def test_anomaly_after_training(client):
    seed_history(client, pc_id="pc-S3", slot="class", n=60)

    # P1-2: dos_spike now requires min_sustained_count consecutive hits
    # of (ratio + absolute floor). Prime the streak with one anomaly call
    # before the assertion call so the second hit fires the signal.
    payload = anomaly_metrics(pc_id="pc-S3", slot="class", idx=300)
    client.post("/analyze", json=payload)
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["overall_severity"] in {"LOW", "MEDIUM", "HIGH"}
    assert body["verdict"] in {
        "OBSERVE", "SUSPICIOUS", "HIGH_RISK",
    }
    assert body["agent"] is not None


# ──────────────────────────────────────────
# 시나리오 4: 게임/컴파일 컨텍스트 감점
# ──────────────────────────────────────────
def test_context_game_compile_discount(client):
    # baseline anomaly score
    seed_history(client, pc_id="pc-S4a", slot="class", n=60)
    r_base = client.post("/analyze",
                         json=anomaly_metrics(pc_id="pc-S4a", slot="class", idx=300))
    base_body = r_base.json()
    base_score = base_body["scores"]["adjusted"]
    base_mult  = base_body["scores"]["context_multiplier"]

    # game ctx
    seed_history(client, pc_id="pc-S4b", slot="class", n=60)
    r_game = client.post("/analyze",
                         json=context_metrics("game", pc_id="pc-S4b",
                                              slot="class", idx=300))
    g_body = r_game.json()
    g_score = g_body["scores"]["adjusted"]
    g_mult  = g_body["scores"]["context_multiplier"]

    # compile ctx
    seed_history(client, pc_id="pc-S4c", slot="class", n=60)
    r_comp = client.post("/analyze",
                         json=context_metrics("compile", pc_id="pc-S4c",
                                              slot="class", idx=300))
    c_body = r_comp.json()
    c_score = c_body["scores"]["adjusted"]
    c_mult  = c_body["scores"]["context_multiplier"]

    # multiplier 감점 확인
    assert base_mult == 1.0
    assert g_mult < 1.0
    assert c_mult < 1.0
    # adjusted score 도 감점 (process score 제외분)
    assert g_score <= base_score
    assert c_score <= base_score
