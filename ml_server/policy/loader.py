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
class ScoringPolicy:
    version: str
    thresholds: Thresholds
    limits: Limits
    scores: Scores
    context_discounts: ContextDiscounts


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
    )
    _scoring_policy_cache = policy
    return policy


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
    """테스트용: 캐시 초기화 후 재로드."""
    global _scoring_policy_cache, _allowlist_cache
    _scoring_policy_cache = None
    _allowlist_cache = None
    load_scoring_policy()
    load_allowlist()


__all__ = [
    "ScoringPolicy",
    "Thresholds",
    "Limits",
    "Scores",
    "ContextDiscounts",
    "AllowList",
    "load_scoring_policy",
    "load_allowlist",
    "get_scoring_policy",
    "get_allowlist",
    "reload_policies",
    "PolicyValidationError",
]
