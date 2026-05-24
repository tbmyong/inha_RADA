"""Layer 4 — verdict 분류 + alerts 생성 + 패턴 분석 진입점.

verdict 4단계 (CONFIRMED_MINING은 HIGH_RISK로 통합, alerts[0].type 으로 표현):
  HIGH_RISK   : final_score >= 14
  SUSPICIOUS  : final_score >=  9
  OBSERVE     : final_score >=  5
  NORMAL      : final_score <   5
"""
from typing import Dict, Any, Tuple, List, Optional
from collections import deque

from ..model.requests import MetricsRequest
from ..storage import score_history_store
from ..policy import get_scoring_policy
from .signal_extractor import extract_signals
from .indicator_calculator import calculate_indicators
from .context_multiplier import apply_context_multiplier


# P0-3 (docs/fp_field_analysis_v0.6.md §7-P0-3): score_breakdown 9키 중
# 어떤 키가 "카테고리" 로서 active_categories 산출에 쓰이는지.
# context_discount / final 은 카테고리가 아니므로 제외.
_BREAKDOWN_CATEGORY_KEYS = (
    "resource", "network", "process", "episode",
    "correlation", "ml", "retrieval",
)

# 신호 → 카테고리 매핑 (active_categories 산출용). signal_extractor 의
# signal 이름을 breakdown 의 카테고리 키로 묶는다. is_gaming/is_compiling 은
# context flag 이므로 제외.
_SIGNAL_TO_CATEGORY: Dict[str, str] = {
    # resource
    "gpu_active": "resource", "gpu_high": "resource", "gpu_flat": "resource",
    "gpu_cpu_gap": "resource", "vram_low": "resource", "vram_stable": "resource",
    "power_stable": "resource", "tensor_inactive": "resource", "sm_high": "resource",
    "stealth_mismatch_power": "resource", "stealth_mismatch_vram": "resource",
    "cpu_high": "resource", "cpu_flat": "resource",
    "mem_high": "resource", "mem_critical": "resource",
    # network
    "net_external_high": "network", "mining_pool_ip": "network",
    "outbound_spike": "network", "dos_spike": "network",
    "net_out_sustained": "network", "disk_write_net_out_sustained": "network",
    "new_remote_ip_burst": "network", "spike_count_1m": "network",
    "persistent_ext": "network",
    # process
    "known_miner": "process", "temp_exec": "process", "appdata_exec": "process",
    "exec_path_suspicious": "process", "unknown_process_active": "process",
    "persistent_miner": "process", "mining_process_or_pool": "process",
    # ml
    "ml_anomaly": "ml",
}


def _build_evidence_meta(signals: Dict[str, Any],
                         breakdown: Dict[str, float],
                         indicators: Dict[str, int],
                         alerts: List[dict]) -> Dict[str, Any]:
    """Active signal/category 집계 + fast-path 식별. analyze_router 에서
    category_gating 발화 시 fast_path_match='confirmed_sustained' 로 덮어쓴다."""
    active_signals = [
        k for k, v in signals.items()
        if v is True and k not in ("is_gaming", "is_compiling")
    ]
    # active_categories: breakdown 의 카테고리 키 중 점수 > 0 인 것 +
    # signal→category 매핑으로 발화한 카테고리 (둘 union).
    active_cats = set()
    for k in _BREAKDOWN_CATEGORY_KEYS:
        try:
            if float(breakdown.get(k, 0) or 0) > 0:
                active_cats.add(k)
        except (TypeError, ValueError):
            pass
    for sig in active_signals:
        cat = _SIGNAL_TO_CATEGORY.get(sig)
        if cat:
            active_cats.add(cat)

    # fast_path_match 결정
    fast_path: Optional[str] = None
    if indicators.get("process", 0) >= 10:
        fast_path = "mining_known"
    if fast_path is None:
        for a in alerts:
            if a.get("type") == "CONFIRMED_MINING":
                fast_path = "alerts_contain_confirmed_mining"
                break

    return {
        "active_signal_count": len(active_signals),
        "category_count":      len(active_cats),
        "active_categories":   sorted(active_cats),
        "active_signals":      sorted(active_signals),
        "promotion_gated":     False,
        "promotion_reason":    "",
        "fast_path_match":     fast_path,
    }


def apply_promotion_gating(verdict: str,
                            evidence_meta: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """P0-3 gating: 단일 신호 MEDIUM/HIGH 진입 차단.

    - fast_path_match 가 있으면 우회 (즉시 HIGH_RISK 유지, MEDIUM 도 그대로).
    - HIGH_RISK 진입: signal>=high_min AND category>=high_min_cat 미달 →
      한 단계 강등 (HIGH_RISK → SUSPICIOUS).
    - SUSPICIOUS 진입: signal>=medium_min AND category>=medium_min_cat 미달 →
      OBSERVE 로 강등.
    - OBSERVE/NORMAL 은 변경 없음.
    """
    meta = dict(evidence_meta)
    try:
        pg = get_scoring_policy().promotion_gating
    except Exception:
        pg = None

    if pg is None or not pg.enabled:
        meta["promotion_reason"] = "gating_disabled"
        return verdict, meta

    fast_path = meta.get("fast_path_match")
    if fast_path:
        meta["promotion_reason"] = f"fast_path:{fast_path}"
        meta["promotion_gated"] = False
        return verdict, meta

    sig_count = int(meta.get("active_signal_count", 0))
    cat_count = int(meta.get("category_count", 0))

    if verdict == "HIGH_RISK":
        ok = (sig_count >= pg.high_min_signal_count
              and cat_count >= pg.high_min_category_count)
        if ok:
            meta["promotion_reason"] = "gating_passed"
            meta["promotion_gated"] = False
            return "HIGH_RISK", meta
        # downgrade — HIGH_RISK 신뢰 부족 → SUSPICIOUS 도 동일 조건 검사
        meta["promotion_gated"] = True
        ok_med = (sig_count >= pg.medium_min_signal_count
                  and cat_count >= pg.medium_min_category_count)
        if ok_med:
            meta["promotion_reason"] = (
                f"gating_blocked:high(sig={sig_count}<{pg.high_min_signal_count}"
                f" or cat={cat_count}<{pg.high_min_category_count})"
            )
            return "SUSPICIOUS", meta
        meta["promotion_reason"] = (
            f"gating_blocked:high+medium(sig={sig_count},cat={cat_count})"
        )
        return "OBSERVE", meta

    if verdict == "SUSPICIOUS":
        ok = (sig_count >= pg.medium_min_signal_count
              and cat_count >= pg.medium_min_category_count)
        if ok:
            meta["promotion_reason"] = "gating_passed"
            meta["promotion_gated"] = False
            return "SUSPICIOUS", meta
        meta["promotion_gated"] = True
        meta["promotion_reason"] = (
            f"gating_blocked:medium(sig={sig_count}<{pg.medium_min_signal_count}"
            f" or cat={cat_count}<{pg.medium_min_category_count})"
        )
        return "OBSERVE", meta

    # OBSERVE / NORMAL — no gating applied
    meta["promotion_reason"] = "gating_not_applicable"
    return verdict, meta


def _build_breakdown(indicators: Dict[str, int],
                     context_discount: int,
                     final_score: float,
                     retrieval_score: int = 0) -> Dict[str, float]:
    """9키 breakdown 조립 (retrieval 추가).

    final = 7개 합(resource+network+process+episode+correlation+ml+retrieval) +
    context_discount (≥ 0 clamp). final 자체는 누적 가중 후 score_history_store
    가 결정한 값을 사용한다.
    """
    resource    = int(indicators.get("breakdown_resource", 0))
    network     = int(indicators.get("breakdown_network", 0))
    process_b   = int(indicators.get("breakdown_process", 0))
    episode     = int(indicators.get("breakdown_episode", 0))
    correlation = int(indicators.get("breakdown_correlation", 0))
    ml_b        = int(indicators.get("breakdown_ml", 0))
    discount    = int(context_discount)
    return {
        "resource":         resource,
        "network":          network,
        "process":          process_b,
        "episode":          episode,
        "correlation":      correlation,
        "ml":               ml_b,
        "retrieval":        int(retrieval_score),
        "context_discount": discount,
        "final":            round(final_score, 2),
    }


def classify_verdict(final_score: float, process_score: int) -> Tuple[str, str]:
    # CONFIRMED_MINING은 별도 verdict가 아닌 HIGH_RISK로 통합 (채굴 확인은 alerts[0].type으로 표현).
    th = get_scoring_policy().thresholds
    if final_score >= th.high_risk:
        return "HIGH_RISK", "HIGH"
    if final_score >= th.suspicious:
        return "SUSPICIOUS", "MEDIUM"
    if final_score >= th.observe:
        return "OBSERVE", "LOW"
    return "NORMAL", "NORMAL"


def build_alerts(verdict: str, signals: Dict[str, Any], indicators: Dict[str, int],
                 final_score: float, known_miners: list, mining_pool_ip_str: str,
                 metrics: MetricsRequest, avg_inbound: float, dos_ratio: int,
                 is_gaming: bool, is_compiling: bool) -> List[dict]:
    alerts: List[dict] = []

    # CONFIRMED_MINING은 verdict가 아닌 alerts[0].type 으로 표현 (정보 보존).
    is_confirmed_mining = indicators["process"] >= 10
    if is_confirmed_mining:
        miner_names = [m["name"] for m in known_miners]
        pool_note   = f" + 채굴풀IP({mining_pool_ip_str})" if signals.get("mining_pool_ip") else ""
        alerts.append({"type":"CONFIRMED_MINING","severity":"HIGH",
                       "detail":f"채굴 프로세스: {miner_names}{pool_note}",
                       "score":round(final_score,2)})
        if signals["persistent_miner"]:
            alerts.append({"type":"PROCESS_PERSISTENT","severity":"HIGH",
                           "detail":"채굴 프로세스 히스토리 6회 이상 지속",
                           "score":round(final_score,2)})

    if verdict in ("HIGH_RISK","SUSPICIOUS","OBSERVE") and not is_confirmed_mining:
        # P2 (docs/fp_field_analysis_post_p1.md §10): BACKDOOR 는 top_cat
        # 후보에서 제외. indicator_calculator 에서 backdoor_score 를 0 으로
        # 고정했으므로 함께 두면 항상 0 → 운영상 무의미한 후보가 alert 의
        # type 으로 채택될 수 있음. raw 신호 (persistent_ext, net_external_high)
        # 는 evidence_meta.active_signals 에 그대로 노출되니 운영자가 별도
        # 확인 가능. Sysmon 데이터 도입 후 재추가 예정.
        top_cat = max([
            ("GPU_MINING", indicators["gpu_mining"]),
            ("CPU_MINING", indicators["cpu_mining"]),
            ("STEALTH",    indicators["stealth"]),
            ("EXFIL",      indicators["exfil"]),
            ("DOS",        indicators["dos"]),
            ("MEMORY",     indicators["mem"]),
            ("ML",         indicators["ml"]),
        ], key=lambda x: x[1])
        active = [k for k, v in signals.items()
                  if v is True and k not in ("is_gaming","is_compiling")]
        ctx = []
        if is_gaming:    ctx.append("게임(-60%)")
        if is_compiling: ctx.append("컴파일(-50%)")
        alerts.append({
            "type":     f"{verdict}_{top_cat[0]}",
            "severity": {"HIGH_RISK":"HIGH","SUSPICIOUS":"MEDIUM","OBSERVE":"LOW"}[verdict],
            "detail":   (f"점수={final_score:.1f} 주요원인={top_cat[0]}({top_cat[1]}점) "
                         f"활성신호={active}"
                         + (f" 컨텍스트감점={ctx}" if ctx else "")),
            "score":    round(final_score, 2),
        })

    if signals["dos_spike"] and avg_inbound > 0:
        alerts.append({"type":"DOS_SUSPECTED","severity":"HIGH",
                       "detail":(f"Inbound 급증 {metrics.inbound_mb:.3f}MB/5s "
                                 f"(평균={avg_inbound:.3f}, "
                                 f"{metrics.inbound_mb/avg_inbound:.1f}배, 기준={dos_ratio}배)"),
                       "score":round(indicators["dos"],2)})

    # P1-1 (docs/fp_field_analysis_v0.6.md §7-P1-1): local alert 는
    # alerts[] 에 섞지 않는다. build_local_evidence() 가 별도 evidence
    # 블록으로 분리해 active_signal_count / verdict 결정에서 빼고
    # 감사 용도로만 보존한다. (build_local_evidence 는 별도 호출.)

    return alerts


def build_local_evidence(metrics: MetricsRequest) -> List[dict]:
    """P1-1 local_alerts 를 별도 evidence 블록으로 변환.

    Spec: LOCAL_* 은 alerts[] 에 더 이상 들어가지 않는다. 하지만 감사
    /검색 목적으로 응답 안에 보존돼야 한다. 본 함수는 client 가 보낸
    metrics.local_alerts (severity HIGH/MEDIUM 만) 를 LOCAL_<type> 형식
    의 evidence 항목 리스트로 반환한다. severity LOW/None 은 제외.

    evidence 항목은 alerts schema 와 호환 (type/severity/detail/score) 이지만
    score=0 이며 evidence_meta.active_signal_count 산출에서 제외된다.
    """
    out: List[dict] = []
    for la in (metrics.local_alerts or []):
        if la.get("severity") in ("HIGH", "MEDIUM"):
            out.append({
                "type":     f"LOCAL_{la.get('type', 'UNKNOWN')}",
                "severity": la["severity"],
                "detail":   f"[에이전트] {la.get('detail', '')}",
                "score":    0,
            })
    return out


def analyze_pattern(metrics: MetricsRequest, history: deque, slot: str,
                    ml_weighted_score: float = 0.0,
                    retrieval_evidence: dict = None) -> dict:
    """Layer 1~4 통합 패턴 분석 (기존 ml_server.py analyze_pattern 동치)."""
    pc_id = metrics.pc_id

    # Layer 1
    sig_pack = extract_signals(metrics, history, slot, ml_weighted_score)
    signals      = sig_pack["signals"]
    is_gaming    = sig_pack["is_gaming"]
    is_compiling = sig_pack["is_compiling"]

    # Layer 2
    indicators = calculate_indicators(signals, slot, ml_weighted_score, sig_pack=sig_pack)

    # Layer 3 — 컨텍스트 감점 (multiplier 호환 + 신규 discount 메타)
    raw_score, adjusted_score, multiplier = apply_context_multiplier(
        indicators, is_gaming, is_compiling,
        signals=signals, metrics=metrics, slot=slot,
    )
    context_discount = getattr(apply_context_multiplier, "_last_discount", 0)
    context_discount_clamped = getattr(apply_context_multiplier, "_last_clamped", False)

    # retrieval score 반영 (context discount 전 점수에 가산)
    retrieval_score_raw = 0
    if isinstance(retrieval_evidence, dict) and retrieval_evidence.get("available"):
        try:
            retrieval_score_raw = int(retrieval_evidence.get("retrieval_score", 0) or 0)
        except (TypeError, ValueError):
            retrieval_score_raw = 0
    # P1-4 (docs/fp_field_analysis_v0.6.md §7-P1-4): retrieval positive
    # score 는 단독으로 verdict 승격에 기여하지 못한다. retrieval_score >= 3
    # 이면서 다른 카테고리 evidence (breakdown 의 resource/network/process/
    # episode/correlation/ml 중 점수 > 0 인 카테고리) 가 2 개 이상일 때만
    # 점수 가산. 그 외에는 0 으로 잠그고 retrieval_evidence 본문은 그대로
    # 유지 (검색/감사 용도). negative retrieval score 는 영향 없음 (gating
    # 무관 그대로 가산).
    _other_cats_positive = sum(
        1 for k in ("breakdown_resource", "breakdown_network",
                    "breakdown_process", "breakdown_episode",
                    "breakdown_correlation", "breakdown_ml")
        if int(indicators.get(k, 0) or 0) > 0
    )
    retrieval_gated = False
    if retrieval_score_raw >= 3 and _other_cats_positive < 2:
        retrieval_score = 0
        retrieval_gated = True
    else:
        retrieval_score = retrieval_score_raw
    if isinstance(retrieval_evidence, dict):
        # 본문에 gating 결과를 노출 (감사/디버그용)
        retrieval_evidence["retrieval_score_effective"] = int(retrieval_score)
        retrieval_evidence["retrieval_score_gated"] = bool(retrieval_gated)
    adjusted_score = adjusted_score + retrieval_score
    # R2: retrieval/context 감점이 score 를 음수로 끌어내려 moving average 를
    # 오염시키는 것을 방지 — adjusted_score 의 하한은 0. (raw_score 는 영향 없음)
    if adjusted_score < 0:
        adjusted_score = 0

    # 누적 가중 평균 (최근 5건)
    final_score = score_history_store.append_rule_score(
        pc_id, slot, adjusted_score, maxlen=5
    )

    # Layer 4 — verdict
    verdict, _severity = classify_verdict(final_score, indicators["process"])

    # alerts
    alerts = build_alerts(
        verdict, signals, indicators, final_score,
        sig_pack["known_miners"], sig_pack["mining_pool_ip_str"],
        metrics, sig_pack["avg_inbound"], sig_pack["dos_ratio"],
        is_gaming, is_compiling,
    )

    # P1-1: local alert evidence (LOCAL_*) — separated from alerts[].
    local_evidence = build_local_evidence(metrics)

    # P0-3 (docs/fp_field_analysis_v0.6.md §7-P0-3): evidence_meta 생성 +
    # promotion gating 적용. 단일 신호로 MEDIUM/HIGH 진입을 막되,
    # mining_known / CONFIRMED_MINING fast-path 는 우회. category_gating
    # 의 confirmed_sustained 우회는 analyze_router 가 후처리.
    breakdown_for_meta = _build_breakdown(
        indicators,
        context_discount=getattr(apply_context_multiplier, "_last_discount", 0),
        final_score=final_score,
        retrieval_score=retrieval_score,
    )
    evidence_meta = _build_evidence_meta(signals, breakdown_for_meta, indicators, alerts)
    verdict, evidence_meta = apply_promotion_gating(verdict, evidence_meta)

    # P0-2 (docs/fp_field_analysis_v0.6.md §7-P0-2):
    # overall_severity 는 engine verdict 가 진실. alert 의 severity 가
    # 자체적으로 overall_severity 를 강제 승격하지 못한다 (=local alert
    # override 제거). 707건의 severity↔verdict 불일치 (MEDIUM/NORMAL
    # 404 + HIGH/OBSERVE 155 등) 의 원인.
    #
    # Fast-path 보존: classify_verdict 가 이미 mining_known + indicators
    # ["process"] 를 본다. xmrig 같은 명백한 mining 은 verdict=HIGH_RISK
    # 로 분류되므로 이 매핑만으로 자동 HIGH 가 된다. 별도 fast-path 분기
    # 불필요.
    _VERDICT_TO_SEVERITY = {
        "HIGH_RISK":  "HIGH",
        "SUSPICIOUS": "MEDIUM",
        "OBSERVE":    "LOW",
        "NORMAL":     "NORMAL",
    }
    overall = _VERDICT_TO_SEVERITY.get(verdict, "NORMAL")

    try:
        policy_version = get_scoring_policy().version
    except Exception:
        policy_version = "unknown"

    return {
        "timetable_slot":   slot,
        "overall_severity": overall,
        "alerts":           alerts,
        "local_evidence":   local_evidence,
        "verdict":          verdict,
        "policy_version":   policy_version,
        "signals_missing":  sig_pack.get("signals_missing", []),
        "evidence_meta":    evidence_meta,
        "scores": {
            "final":              round(final_score, 2),
            "adjusted":           round(adjusted_score, 2),
            "raw":                round(raw_score, 2),
            "gpu_mining":         indicators["gpu_mining"],
            "cpu_mining":         indicators["cpu_mining"],
            "stealth":            indicators["stealth"],
            "exfil":              indicators["exfil"],
            "process":            indicators["process"],
            "dos":                indicators["dos"],
            "backdoor":           indicators["backdoor"],
            "mem":                indicators["mem"],
            "ml":                 indicators["ml"],
            "context_multiplier": round(multiplier, 2),
            "score_breakdown": _build_breakdown(
                indicators, context_discount, final_score, retrieval_score
            ),
            "context_discount_clamped": bool(context_discount_clamped),
        },
        "signals": {k: bool(v) if not isinstance(v, bool) else v
                    for k, v in signals.items()},
    }
