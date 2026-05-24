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
from ..scorer import pattern_categories, category_gating
from ..policy import get_scoring_policy
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

    # v0.6: 1분 aggregate 버퍼 (3h 윈도우) 누적
    df = metrics.derived_features or {}
    user_idle_ms = None
    try:
        if isinstance(df, dict):
            user_idle_ms = df.get("user_idle_ms")
    except Exception:
        user_idle_ms = None
    external_endpoints = [
        c.get("ip", "") for c in (metrics.external_connections or [])
        if isinstance(c, dict) and c.get("ip")
    ]
    pc_history_store.append_snapshot_for_aggregate(
        pc_id, snapshot,
        external_endpoints=external_endpoints,
        user_idle_ms=user_idle_ms,
        memory_used_gb=metrics.memory_used_gb,
    )

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

    # v0.6: 카테고리 패턴 evaluator + 게이팅
    try:
        policy = get_scoring_policy()
        cat_cfg = {
            "resource": policy.category_patterns.group("resource"),
            "network":  policy.category_patterns.group("network"),
            "system":   policy.category_patterns.group("system"),
        }
        gating_cfg = {"gating": {
            "mining_confirmed": policy.gating.get("mining_confirmed"),
            "suspicious":       policy.gating.get("suspicious"),
            "observe":          policy.gating.get("observe"),
        }}
        # 현재 진행 중인 1분 버퍼도 즉시 보이도록 flush
        pc_history_store.force_flush_minute_buffer(pc_id)
        history_window = pc_history_store.get_aggregate_window(pc_id, minutes=180)
        current_snapshot = {
            "cpu_percent": metrics.cpu_percent,
            "gpu_percent": metrics.gpu.load_percent if metrics.gpu else 0.0,
            "memory_used_gb": metrics.memory_used_gb,
        }
        res_cat = pattern_categories.evaluate_resource_pattern(history_window, current_snapshot, cat_cfg)
        net_cat = pattern_categories.evaluate_network_pattern(history_window, current_snapshot, cat_cfg)
        sys_cat = pattern_categories.evaluate_system_pattern(history_window, current_snapshot, cat_cfg)
        state = pc_history_store.get_category_state(pc_id)
        gating_result = category_gating.evaluate(res_cat, net_cat, sys_cat, state, gating_cfg)

        triggered = (
            list(res_cat.triggered_patterns)
            + list(net_cat.triggered_patterns)
            + list(sys_cat.triggered_patterns)
        )
        category_signals = {
            "resource_abnormal":   bool(res_cat.abnormal),
            "network_abnormal":    bool(net_cat.abnormal),
            "system_abnormal":     bool(sys_cat.abnormal),
            "sustained_minutes":   int(gating_result.sustained_minutes),
            "triggered_patterns":  triggered,
            "verdict_from_gating": gating_result.verdict,
        }
        pattern_result["category_signals"] = category_signals

        # 두 경로 OR — 더 강한 verdict 채택 (verdict 순위: HIGH_RISK > SUSPICIOUS > OBSERVE > NORMAL)
        verdict_rank = {"HIGH_RISK": 3, "SUSPICIOUS": 2, "OBSERVE": 1, "NORMAL": 0}
        cur_v = pattern_result.get("verdict", "NORMAL")
        gv = gating_result.verdict
        # P0-3: category_gating 의 mining_confirmed (alert_type ==
        # MINING_CONFIRMED_BY_BEHAVIOR) 는 promotion gating 의 fast-path
        # "confirmed_sustained" 로 표시. evidence_meta 에 즉시 반영.
        if gating_result.detail.get("alert_type") == "MINING_CONFIRMED_BY_BEHAVIOR":
            em = pattern_result.get("evidence_meta") or {}
            em["fast_path_match"] = "confirmed_sustained"
            em["promotion_gated"] = False
            em["promotion_reason"] = "fast_path:confirmed_sustained"
            pattern_result["evidence_meta"] = em
        if verdict_rank.get(gv, 0) > verdict_rank.get(cur_v, 0):
            pattern_result["verdict"] = gv
            sev_map = {"HIGH_RISK": "HIGH", "SUSPICIOUS": "MEDIUM", "OBSERVE": "LOW", "NORMAL": "NORMAL"}
            new_sev = sev_map[gv]
            cur_sev = pattern_result.get("overall_severity", "NORMAL")
            sev_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NORMAL": 0}
            if sev_rank.get(new_sev, 0) > sev_rank.get(cur_sev, 0):
                pattern_result["overall_severity"] = new_sev
            # alert append (behavior-based)
            alert_type = gating_result.detail.get("alert_type") or f"{gv}_BEHAVIOR"
            pattern_result["alerts"].append({
                "type":     alert_type,
                "severity": new_sev if new_sev != "NORMAL" else "LOW",
                "detail":   (f"category_gating verdict={gv} cats={gating_result.cats_count} "
                             f"sustained_min={gating_result.sustained_minutes} "
                             f"triggered={triggered}"),
                "score":    0,
            })
    except Exception as _cat_e:
        # fail-open: 카테고리 평가 실패는 기존 verdict 에 영향 주지 않음
        pattern_result["category_signals"] = {
            "resource_abnormal":   False,
            "network_abnormal":    False,
            "system_abnormal":     False,
            "sustained_minutes":   0,
            "triggered_patterns":  [],
            "verdict_from_gating": "NORMAL",
            "error": str(_cat_e),
        }

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

    # 전체 PC 노후화 — alert 로만 첨부, overall_severity 변경 X.
    # P0-2 (docs/fp_field_analysis_v0.6.md §7-P0-2): alert evidence 가
    # severity 를 강제 승격하지 못한다. GLOBAL_HW_DEGRADATION 은 운영
    # 관찰용 evidence 로만 보존.
    global_hw = detect_global_hw_degradation()
    if global_hw.get("detected"):
        pattern_result["alerts"].append({
            "type":     "GLOBAL_HW_DEGRADATION",
            "severity": "MEDIUM",
            "detail":   global_hw["detail"],
        })

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
        "local_evidence":      pattern_result.get("local_evidence", []),
        "signals_missing":     pattern_result.get("signals_missing", []),
        "category_signals":    pattern_result.get("category_signals", {
            "resource_abnormal":   False,
            "network_abnormal":    False,
            "system_abnormal":     False,
            "sustained_minutes":   0,
            "triggered_patterns":  [],
            "verdict_from_gating": "NORMAL",
        }),
        "evidence_meta":       pattern_result.get("evidence_meta", {
            "active_signal_count": 0,
            "category_count":      0,
            "active_categories":   [],
            "active_signals":      [],
            "promotion_gated":     False,
            "promotion_reason":    "gating_disabled",
            "fast_path_match":     None,
        }),
    })
