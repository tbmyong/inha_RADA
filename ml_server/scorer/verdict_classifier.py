"""Layer 4 — verdict 분류 + alerts 생성 + 패턴 분석 진입점.

verdict 4단계 (CONFIRMED_MINING은 HIGH_RISK로 통합, alerts[0].type 으로 표현):
  HIGH_RISK   : final_score >= 14
  SUSPICIOUS  : final_score >=  9
  OBSERVE     : final_score >=  5
  NORMAL      : final_score <   5
"""
from typing import Dict, Any, Tuple, List
from collections import deque

from ..model.requests import MetricsRequest
from ..storage import score_history_store
from ..policy import get_scoring_policy
from .signal_extractor import extract_signals
from .indicator_calculator import calculate_indicators
from .context_multiplier import apply_context_multiplier


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
        top_cat = max([
            ("GPU_MINING", indicators["gpu_mining"]),
            ("CPU_MINING", indicators["cpu_mining"]),
            ("STEALTH",    indicators["stealth"]),
            ("EXFIL",      indicators["exfil"]),
            ("BACKDOOR",   indicators["backdoor"]),
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

    for la in metrics.local_alerts:
        if la.get("severity") in ("HIGH","MEDIUM"):
            alerts.append({"type":f"LOCAL_{la.get('type','UNKNOWN')}",
                           "severity":la["severity"],
                           "detail":f"[에이전트] {la.get('detail','')}",
                           "score":0})

    return alerts


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
    retrieval_score = 0
    if isinstance(retrieval_evidence, dict) and retrieval_evidence.get("available"):
        try:
            retrieval_score = int(retrieval_evidence.get("retrieval_score", 0) or 0)
        except (TypeError, ValueError):
            retrieval_score = 0
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
        "verdict":          verdict,
        "policy_version":   policy_version,
        "signals_missing":  sig_pack.get("signals_missing", []),
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
