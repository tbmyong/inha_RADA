"""POST /analyze — 메인 분석 엔드포인트."""
import datetime
import time as _time
from typing import Any
import numpy as np
from fastapi import APIRouter

from ..config import get_timetable_slot
from ..feature.feature_builder import make_snapshot
from ..model.requests import MetricsRequest
from ..storage import pc_history_store
from ..scheduler.retraining_scheduler import maybe_retrain
from ..detector.anomaly_predictor import predict_anomaly
from ..detector.global_degradation import detect_global_hw_degradation
from ..scorer.verdict_classifier import analyze_pattern
from ..agent.runner import run_ai_agent
from ..retrieval import (
    build_segment,
    build_embedding,
    search_similar,
    add_segment,
    build_retrieval_evidence,
)

router = APIRouter()


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(i) for i in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


@router.post("/analyze")
def analyze(metrics: MetricsRequest):
    pc_id = metrics.pc_id
    dt    = datetime.datetime.fromisoformat(metrics.timestamp)
    slot  = get_timetable_slot(dt)

    history = pc_history_store.ensure_pc_history(pc_id)
    snapshot = make_snapshot(metrics)
    history.append(snapshot)
    pc_history_store.update_train_history(pc_id, slot, snapshot)

    pc_history_store.all_pc_latest[pc_id] = {
        "cpu_percent":           metrics.cpu_percent,
        "memory_percent":        metrics.memory_percent,
        "timestamp":             metrics.timestamp,
        "slot":                  slot,
        "inbound_mb":            metrics.inbound_mb,
        "outbound_mb":           metrics.outbound_mb,
        "disk_read_mb":          metrics.disk_read_mb,
        "disk_write_mb":         metrics.disk_write_mb,
        "gpu_percent":           metrics.gpu.load_percent if metrics.gpu else 0.0,
        "external_packet_count": metrics.external_packet_count,
        "_ts":                   _time.time(),
    }

    # 재학습
    maybe_retrain(pc_id, slot)

    # ML 앙상블
    if_result = predict_anomaly(pc_id, slot, metrics)
    ml_weighted = if_result.get("weighted_score") or 0.0

    # Retrieval evidence (segment → embedding → top-k 검색)
    current_segment = build_segment(pc_id, slot, history, window_size=12)
    retrieval_evidence = None
    current_embedding = None
    if current_segment is not None:
        current_embedding = build_embedding(current_segment)
        retrieved = search_similar(current_segment, current_embedding, top_k=3)
        retrieval_evidence = build_retrieval_evidence(
            current_segment, retrieved,
            peer_latest=pc_history_store.all_pc_latest,
        )

    # 패턴 분석
    pattern_result = analyze_pattern(metrics, history, slot,
                                     ml_weighted_score=ml_weighted,
                                     retrieval_evidence=retrieval_evidence)
    if retrieval_evidence is not None:
        pattern_result["retrieval_evidence"] = retrieval_evidence

    # 현재 segment 저장 (검색 이후 → 자기 자신이 top-k 에 잡히지 않음)
    if current_segment is not None and current_embedding is not None:
        try:
            add_segment(
                current_segment, current_embedding,
                verdict=pattern_result.get("verdict", "NORMAL"),
                score=float(pattern_result.get("scores", {}).get("final", 0.0)),
            )
        except Exception:
            pass

    # 전체 PC 노후화
    global_hw = detect_global_hw_degradation()
    if global_hw.get("detected"):
        pattern_result["alerts"].append({
            "type":     "GLOBAL_HW_DEGRADATION",
            "severity": "MEDIUM",
            "detail":   global_hw["detail"],
        })
        if pattern_result["overall_severity"] == "NORMAL":
            pattern_result["overall_severity"] = "MEDIUM"

    # AI Agent
    agent_result = None
    if pattern_result["overall_severity"] != "NORMAL":
        agent_result = run_ai_agent(metrics, pattern_result, global_hw)

    return _sanitize({
        "pc_id":               pc_id,
        "timestamp":           metrics.timestamp,
        "timetable_slot":      slot,
        "overall_severity":    pattern_result["overall_severity"],
        "verdict":             pattern_result.get("verdict", "NORMAL"),
        "policy_version":      pattern_result.get("policy_version", "unknown"),
        "alerts":              pattern_result["alerts"],
        "scores":              pattern_result.get("scores", {}),
        "signals":             pattern_result.get("signals", {}),
        "history_size":        len(history),
        "isolation_forest":    if_result,
        "global_hw_degradation": global_hw,
        "agent":               agent_result,
        "retrieval_evidence":  retrieval_evidence,
    })
