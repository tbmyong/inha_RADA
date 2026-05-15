"""Layer 3 컨텍스트 — 게임/컴파일 배수 (legacy 호환) + 정황 감점(discount).

- 게임/컴파일: 기존 배수(×0.4, ×0.5) 유지 (외부 통합 테스트 호환)
- 정황 감점: startup -1, security_scan -2, maintenance_update -2,
  lab_agent -1, class_or_free -1 (max_context_discount = -4 clamp)
- danger override: 위험 신호 1개라도 True → discount = max(discount, -1)
"""
from __future__ import annotations
from typing import Dict, Tuple, Any, Optional

from ..policy import get_scoring_policy


# 하위 호환 모듈 레벨 (런타임은 정책 기반 동적 lookup 사용)
MAX_CONTEXT_DISCOUNT = -4
_CONTEXT_DISCOUNTS = {
    "startup":            -1,
    "security_scan":      -2,
    "maintenance_update": -2,
    "lab_agent":          -1,
    "class_or_free":      -1,
}


def _ctx_map() -> Dict[str, int]:
    try:
        return dict(get_scoring_policy().context_discounts.raw)
    except Exception:
        return _CONTEXT_DISCOUNTS


def _max_discount() -> int:
    try:
        return int(get_scoring_policy().limits.max_context_discount)
    except Exception:
        return MAX_CONTEXT_DISCOUNT


def _danger_override_clamp() -> int:
    try:
        return int(get_scoring_policy().limits.danger_override_max_discount)
    except Exception:
        return -1


def _collect_context_hints(metrics, signals: Dict[str, Any]) -> list:
    """metrics/signals에서 context 카테고리 라벨을 추출.

    우선순위: derived_features.context_hint > local_alerts > metrics.slot 휴리스틱
    """
    hints: list = []
    ctx_map = _ctx_map()

    df = getattr(metrics, "derived_features", None) or {}
    if isinstance(df, dict):
        ch = df.get("context_hint")
        if isinstance(ch, str) and ch in ctx_map:
            hints.append(ch)
        elif isinstance(ch, list):
            for c in ch:
                if c in ctx_map:
                    hints.append(c)

    # local_alerts 에서 type 기반 카테고리화
    for la in getattr(metrics, "local_alerts", []) or []:
        t = (la.get("type") or "").lower()
        if "startup" in t or "boot" in t:
            hints.append("startup")
        elif "scan" in t or "antivirus" in t or "defender" in t:
            hints.append("security_scan")
        elif "update" in t or "maintenance" in t or "patch" in t:
            hints.append("maintenance_update")
        elif "lab_agent" in t or "lab-agent" in t:
            hints.append("lab_agent")

    return hints


def _compute_context_discount(metrics, signals: Dict[str, Any], slot: str) -> int:
    """카테고리 감점 누적 + class_or_free 기본 감점(slot 정의 시) + clamp."""
    ctx_map = _ctx_map()
    max_disc = _max_discount()

    discount = 0
    seen = set()
    for h in _collect_context_hints(metrics, signals):
        if h in seen:
            continue
        seen.add(h)
        discount += int(ctx_map.get(h, 0))

    # slot이 정의돼 있고 다른 감점이 전혀 없으면 class_or_free 1회 적용
    if slot in ("class", "free") and not seen:
        discount += int(ctx_map.get("class_or_free", 0))

    if discount < max_disc:
        discount = max_disc
    return discount


def _danger_override(signals: Dict[str, Any]) -> bool:
    """위험 신호 1개라도 True → 감점 강하게 클램프."""
    if signals.get("unknown_process_active") and signals.get("net_out_sustained"):
        return True
    if (signals.get("temp_exec") or signals.get("appdata_exec")) and (
        signals.get("cpu_high") or signals.get("gpu_high")
    ):
        return True
    if signals.get("disk_write_net_out_sustained"):
        return True
    if signals.get("mining_process_or_pool"):
        return True
    return False


def apply_context_multiplier(
    indicators: Dict[str, int],
    is_gaming: bool,
    is_compiling: bool,
    signals: Optional[Dict[str, Any]] = None,
    metrics=None,
    slot: Optional[str] = None,
) -> Tuple[float, float, float]:
    """returns (raw_score, adjusted_score, multiplier).

    - 게임/컴파일 multiplier는 legacy 호환 유지 (process_score 제외).
    - 신규 context_discount는 indicators["context_discount"] (또는 _last_discount)
      에 기록만 하고, adjusted_score 에는 별도 가산하지 않는다
      (score_breakdown.final에서 합산되도록 verdict_classifier가 처리).
    """
    raw_score = (
        indicators["gpu_mining"] +
        indicators["cpu_mining"] +
        indicators["stealth"] +
        indicators["exfil"] +
        indicators["process"] +
        indicators["dos"] +
        indicators["backdoor"] +
        indicators["mem"] +
        indicators["ml"]
    )

    multiplier = 1.0
    if is_gaming:    multiplier *= 0.4
    if is_compiling: multiplier *= 0.5

    process_score = indicators["process"]
    adjusted = process_score + (raw_score - process_score) * multiplier

    # context discount 계산 (signals/metrics가 주어졌을 때만)
    discount = 0
    clamped = False
    if signals is not None:
        discount = _compute_context_discount(metrics, signals, slot or "")
        # danger override
        if _danger_override(signals):
            cap = _danger_override_clamp()
            new_d = max(discount, cap)
            if new_d != discount:
                clamped = True
            discount = new_d

    # 부가 메타 (verdict_classifier가 읽음)
    apply_context_multiplier._last_discount = discount        # type: ignore[attr-defined]
    apply_context_multiplier._last_clamped = clamped          # type: ignore[attr-defined]

    return raw_score, adjusted, multiplier
