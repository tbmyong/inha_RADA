"""scoring_policy.yaml 검증 (8 케이스)."""
from __future__ import annotations
from typing import Any, Dict
import math


class PolicyValidationError(RuntimeError):
    """정책 파일 검증 실패."""


_REQUIRED_TOP_KEYS = ("version", "thresholds", "limits", "scores", "context_discounts")
_REQUIRED_THRESHOLDS = ("observe", "suspicious", "high_risk")
_REQUIRED_LIMITS = ("ml_score_cap", "max_context_discount", "danger_override_max_discount")


def _is_finite_number(x: Any) -> bool:
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, float):
        return not (math.isnan(x) or math.isinf(x))
    return False


def validate_scoring_policy(data: Dict[str, Any]) -> None:
    """raw dict 검증. 실패 시 PolicyValidationError(=RuntimeError) 발생."""
    if not isinstance(data, dict):
        raise PolicyValidationError("scoring_policy.yaml: root must be a mapping")

    # 1) 필수 키 누락
    for k in _REQUIRED_TOP_KEYS:
        if k not in data:
            raise PolicyValidationError(f"missing required top-level key: {k}")

    # 2) version: 비어있지 않은 str
    version = data["version"]
    if not isinstance(version, str) or not version.strip():
        raise PolicyValidationError("version must be a non-empty string")

    # 3) thresholds strict ascending: observe < suspicious < high_risk
    thresholds = data["thresholds"]
    if not isinstance(thresholds, dict):
        raise PolicyValidationError("thresholds must be a mapping")
    for k in _REQUIRED_THRESHOLDS:
        if k not in thresholds:
            raise PolicyValidationError(f"missing thresholds.{k}")
        if not _is_finite_number(thresholds[k]):
            raise PolicyValidationError(f"thresholds.{k} must be a finite number")
    if not (thresholds["observe"] < thresholds["suspicious"] < thresholds["high_risk"]):
        raise PolicyValidationError(
            "thresholds must satisfy observe < suspicious < high_risk (strict ascending)"
        )

    # 4) limits
    limits = data["limits"]
    if not isinstance(limits, dict):
        raise PolicyValidationError("limits must be a mapping")
    for k in _REQUIRED_LIMITS:
        if k not in limits:
            raise PolicyValidationError(f"missing limits.{k}")
        if not _is_finite_number(limits[k]):
            raise PolicyValidationError(f"limits.{k} must be a finite number")

    if limits["ml_score_cap"] < 0:
        raise PolicyValidationError("limits.ml_score_cap must be >= 0")
    if limits["max_context_discount"] > 0:
        raise PolicyValidationError("limits.max_context_discount must be <= 0")
    if limits["danger_override_max_discount"] > 0:
        raise PolicyValidationError("limits.danger_override_max_discount must be <= 0")

    # 5) scores: int/float, NaN/None 거부
    scores = data["scores"]
    if not isinstance(scores, dict):
        raise PolicyValidationError("scores must be a mapping")
    for k, v in scores.items():
        if v is None or not _is_finite_number(v):
            raise PolicyValidationError(
                f"scores.{k} must be a finite number (got {v!r})"
            )

    # 6) context_discounts: 모두 ≤ 0
    cd = data["context_discounts"]
    if not isinstance(cd, dict):
        raise PolicyValidationError("context_discounts must be a mapping")
    for k, v in cd.items():
        if not _is_finite_number(v):
            raise PolicyValidationError(
                f"context_discounts.{k} must be a finite number (got {v!r})"
            )
        if v > 0:
            raise PolicyValidationError(
                f"context_discounts.{k} must be <= 0 (got {v})"
            )
