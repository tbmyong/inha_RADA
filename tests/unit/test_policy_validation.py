"""scoring_policy 검증 — 8 케이스."""
import pytest

from ml_server.policy.validation import (
    validate_scoring_policy,
    PolicyValidationError,
)


def _ok():
    return {
        "version": "1.0.0",
        "thresholds": {"observe": 5, "suspicious": 9, "high_risk": 14},
        "limits": {
            "ml_score_cap": 5,
            "max_context_discount": -4,
            "danger_override_max_discount": -1,
        },
        "scores": {"a": 1, "b": 2.5},
        "context_discounts": {"startup": -1, "class_or_free": -1},
    }


def test_valid_passes():
    validate_scoring_policy(_ok())


def test_thresholds_must_be_strict_ascending():
    d = _ok()
    d["thresholds"] = {"observe": 9, "suspicious": 9, "high_risk": 14}
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)


def test_scores_reject_none_or_nan():
    import math
    d = _ok()
    d["scores"]["bad"] = None
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)
    d = _ok()
    d["scores"]["nan"] = float("nan")
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)


def test_context_discounts_must_be_non_positive():
    d = _ok()
    d["context_discounts"]["bad"] = 1
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)


def test_limits_max_context_discount_non_positive():
    d = _ok()
    d["limits"]["max_context_discount"] = 1
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)


def test_limits_ml_score_cap_non_negative():
    d = _ok()
    d["limits"]["ml_score_cap"] = -1
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)


def test_limits_danger_override_max_discount_non_positive():
    d = _ok()
    d["limits"]["danger_override_max_discount"] = 1
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)


def test_missing_required_keys_raises():
    for k in ("version", "thresholds", "limits", "scores", "context_discounts"):
        d = _ok()
        d.pop(k)
        with pytest.raises(PolicyValidationError):
            validate_scoring_policy(d)


def test_version_must_be_non_empty_string():
    d = _ok()
    d["version"] = ""
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)
    d = _ok()
    d["version"] = 1
    with pytest.raises(PolicyValidationError):
        validate_scoring_policy(d)
