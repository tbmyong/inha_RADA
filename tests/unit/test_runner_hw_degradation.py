"""runner._normalize_hw_degradation — Claude/Mock 응답의 hw_degradation 정규화."""
from ml_server.agent.runner import _normalize_hw_degradation


def test_bool_true_becomes_suspected():
    result = {"hw_degradation": True}
    _normalize_hw_degradation(result)
    assert result["hw_degradation"] == "SUSPECTED"


def test_bool_false_becomes_none():
    result = {"hw_degradation": False}
    _normalize_hw_degradation(result)
    assert result["hw_degradation"] == "NONE"


def test_unknown_string_becomes_none():
    result = {"hw_degradation": "MAYBE"}
    _normalize_hw_degradation(result)
    assert result["hw_degradation"] == "NONE"


def test_none_value_becomes_none():
    result = {"hw_degradation": None}
    _normalize_hw_degradation(result)
    assert result["hw_degradation"] == "NONE"


def test_missing_key_becomes_none():
    result = {}
    _normalize_hw_degradation(result)
    assert result["hw_degradation"] == "NONE"


def test_valid_values_preserved():
    for val in ("NONE", "SUSPECTED", "CONFIRMED"):
        result = {"hw_degradation": val}
        _normalize_hw_degradation(result)
        assert result["hw_degradation"] == val
