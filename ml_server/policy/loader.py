"""YAML 정책 로더 + 캐시.

- `RADA_POLICY_DIR` 환경변수로 디렉토리 override
- 기본값: ml_server/config_yaml/
- 모듈 레벨 1회 캐시 (`reload_policies()` 로 테스트에서 초기화)
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional

import yaml

from .validation import validate_scoring_policy, PolicyValidationError
from ..silent_fail_counters import increment as _bump_silent_fail


# ──────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────
@dataclass(frozen=True)
class Thresholds:
    observe: float
    suspicious: float
    high_risk: float


@dataclass(frozen=True)
class Limits:
    ml_score_cap: int
    max_context_discount: int
    danger_override_max_discount: int


@dataclass(frozen=True)
class Scores:
    raw: Dict[str, float] = field(default_factory=dict)

    def get(self, key: str, default: float = 0.0) -> float:
        return float(self.raw.get(key, default))


@dataclass(frozen=True)
class ContextDiscounts:
    raw: Dict[str, int] = field(default_factory=dict)

    def get(self, key: str, default: int = 0) -> int:
        return int(self.raw.get(key, default))


@dataclass(frozen=True)
class CategoryPatterns:
    """category_patterns YAML section (resource/network/system 그룹).

    각 그룹은 {pattern_name: {threshold: {...}, enabled?: bool}} 의 dict.
    """
    raw: Dict[str, Any] = field(default_factory=dict)

    def group(self, name: str) -> Dict[str, Any]:
        v = self.raw.get(name) or {}
        return v if isinstance(v, dict) else {}


@dataclass(frozen=True)
class Gating:
    raw: Dict[str, Any] = field(default_factory=dict)

    def get(self, tier: str) -> Dict[str, Any]:
        v = self.raw.get(tier) or {}
        return v if isinstance(v, dict) else {}


@dataclass(frozen=True)
class PromotionGating:
    """P0-3 promotion gating (signal_count + category_count 강제)."""
    enabled: bool = False
    medium_min_signal_count: int = 0
    medium_min_category_count: int = 0
    high_min_signal_count: int = 0
    high_min_category_count: int = 0
    fast_path: FrozenSet[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class DosDetection:
    """P1-2 DOS / network spike 절대값 floor + 지속 횟수 조건."""
    min_inbound_mb_per_5s: float = 0.0
    min_sustained_count: int = 1


@dataclass(frozen=True)
class EpisodeDedupe:
    """P1-3 episode score 빠른 decay + alert cooldown.

    - episode_decay_after_normal_count: append_rule_score 가 0 점을 N회
      연속 받으면 deque 를 즉시 비워 누적을 끊는다. 0 = 비활성.
    - alert_cooldown_seconds: Spring 측 dedupe 윈도우 (초). 0 = 비활성.
    """
    episode_decay_after_normal_count: int = 0
    alert_cooldown_seconds: int = 0


@dataclass(frozen=True)
class ScoringPolicy:
    version: str
    thresholds: Thresholds
    limits: Limits
    scores: Scores
    context_discounts: ContextDiscounts
    category_patterns: CategoryPatterns = field(default_factory=CategoryPatterns)
    gating: Gating = field(default_factory=Gating)
    promotion_gating: PromotionGating = field(default_factory=PromotionGating)
    dos_detection: DosDetection = field(default_factory=DosDetection)
    episode_dedupe: EpisodeDedupe = field(default_factory=EpisodeDedupe)


@dataclass(frozen=True)
class AllowList:
    version: str
    whitelist_processes: FrozenSet[str]
    game_render_processes: FrozenSet[str]
    compile_encode_processes: FrozenSet[str]
    mining_processes: FrozenSet[str]
    mining_pool_ip_prefixes: FrozenSet[str]


# ──────────────────────────────────────────
# 캐시
# ──────────────────────────────────────────
_scoring_policy_cache: Optional[ScoringPolicy] = None
_allowlist_cache: Optional[AllowList] = None


def _policy_dir() -> Path:
    override = os.getenv("RADA_POLICY_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "config_yaml"


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"policy file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RuntimeError(f"policy file is not a mapping: {path}")
    return data


def load_scoring_policy() -> ScoringPolicy:
    """파일에서 로드 → 검증 → 캐시 갱신 후 반환."""
    global _scoring_policy_cache
    path = _policy_dir() / "scoring_policy.yaml"
    data = _read_yaml(path)
    validate_scoring_policy(data)

    th = data["thresholds"]
    lm = data["limits"]
    policy = ScoringPolicy(
        version=str(data["version"]),
        thresholds=Thresholds(
            observe=float(th["observe"]),
            suspicious=float(th["suspicious"]),
            high_risk=float(th["high_risk"]),
        ),
        limits=Limits(
            ml_score_cap=int(lm["ml_score_cap"]),
            max_context_discount=int(lm["max_context_discount"]),
            danger_override_max_discount=int(lm["danger_override_max_discount"]),
        ),
        scores=Scores(raw=dict(data["scores"])),
        context_discounts=ContextDiscounts(raw=dict(data["context_discounts"])),
        category_patterns=CategoryPatterns(
            raw=dict(data.get("category_patterns") or {})
        ),
        gating=Gating(raw=dict(data.get("gating") or {})),
        promotion_gating=_build_promotion_gating(data.get("promotion_gating")),
        dos_detection=_build_dos_detection(data.get("dos_detection")),
        episode_dedupe=_build_episode_dedupe(data.get("episode_dedupe")),
    )
    _scoring_policy_cache = policy
    return policy


def _build_dos_detection(raw: Any) -> "DosDetection":
    """P1-2 dos_detection 섹션 파싱. 없으면 비활성 기본값(=floor 0, sustained 1)."""
    if not isinstance(raw, dict):
        return DosDetection()
    try:
        floor = float(raw.get("min_inbound_mb_per_5s", 0.0) or 0.0)
    except (TypeError, ValueError):
        floor = 0.0
    try:
        sustained = int(raw.get("min_sustained_count", 1) or 1)
    except (TypeError, ValueError):
        sustained = 1
    if sustained < 1:
        sustained = 1
    if floor < 0:
        floor = 0.0
    return DosDetection(min_inbound_mb_per_5s=floor, min_sustained_count=sustained)


def _build_episode_dedupe(raw: Any) -> "EpisodeDedupe":
    """P1-3 episode_dedupe 섹션 파싱."""
    if not isinstance(raw, dict):
        return EpisodeDedupe()
    try:
        decay = int(raw.get("episode_decay_after_normal_count", 0) or 0)
    except (TypeError, ValueError):
        decay = 0
    try:
        cooldown = int(raw.get("alert_cooldown_seconds", 0) or 0)
    except (TypeError, ValueError):
        cooldown = 0
    if decay < 0:
        decay = 0
    if cooldown < 0:
        cooldown = 0
    return EpisodeDedupe(
        episode_decay_after_normal_count=decay,
        alert_cooldown_seconds=cooldown,
    )


def _build_promotion_gating(raw: Any) -> "PromotionGating":
    """P0-3 promotion_gating 섹션 파싱. 없으면 disabled 기본값."""
    if not isinstance(raw, dict):
        return PromotionGating()
    medium = raw.get("medium") or {}
    high = raw.get("high") or {}
    fp_raw = raw.get("fast_path") or []
    if not isinstance(fp_raw, list):
        fp_raw = []
    return PromotionGating(
        enabled=bool(raw.get("enabled", False)),
        medium_min_signal_count=int(medium.get("min_signal_count", 0) or 0),
        medium_min_category_count=int(medium.get("min_category_count", 0) or 0),
        high_min_signal_count=int(high.get("min_signal_count", 0) or 0),
        high_min_category_count=int(high.get("min_category_count", 0) or 0),
        fast_path=frozenset(str(x) for x in fp_raw),
    )


def load_allowlist() -> AllowList:
    """allowlist.yaml 로드 → 캐시."""
    global _allowlist_cache
    path = _policy_dir() / "allowlist.yaml"
    data = _read_yaml(path)

    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("allowlist.yaml: version must be a non-empty string")

    def _fset(key: str) -> FrozenSet[str]:
        items = data.get(key) or []
        if not isinstance(items, list):
            raise RuntimeError(f"allowlist.yaml: {key} must be a list")
        return frozenset(str(x) for x in items)

    al = AllowList(
        version=version,
        whitelist_processes=_fset("whitelist_processes"),
        game_render_processes=_fset("game_render_processes"),
        compile_encode_processes=_fset("compile_encode_processes"),
        mining_processes=_fset("mining_processes"),
        mining_pool_ip_prefixes=_fset("mining_pool_ip_prefixes"),
    )
    _allowlist_cache = al
    return al


def get_scoring_policy() -> ScoringPolicy:
    """캐시 우선, 없으면 lazy-load."""
    if _scoring_policy_cache is None:
        return load_scoring_policy()
    return _scoring_policy_cache


def get_allowlist() -> AllowList:
    if _allowlist_cache is None:
        return load_allowlist()
    return _allowlist_cache


def reload_policies() -> None:
    """테스트용: 캐시 초기화 후 재로드.

    fail-fast 정책 유지: 실패 시 예외를 그대로 전파한다.
    silent_fail_counters 의 policy_reload_failed_count 는 관측 목적으로만 증가.
    """
    global _scoring_policy_cache, _allowlist_cache
    _scoring_policy_cache = None
    _allowlist_cache = None
    try:
        load_scoring_policy()
        load_allowlist()
    except Exception:
        _bump_silent_fail("policy_reload_failed_count")
        raise


__all__ = [
    "ScoringPolicy",
    "Thresholds",
    "Limits",
    "Scores",
    "ContextDiscounts",
    "CategoryPatterns",
    "Gating",
    "PromotionGating",
    "DosDetection",
    "EpisodeDedupe",
    "AllowList",
    "load_scoring_policy",
    "load_allowlist",
    "get_scoring_policy",
    "get_allowlist",
    "reload_policies",
    "PolicyValidationError",
]
