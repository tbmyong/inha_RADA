"""agent_core.sender.sanitize_for_json 테스트."""
import json

import numpy as np

from agent_core.sender import sanitize_for_json


def test_numpy_bool_converted():
    out = sanitize_for_json({"flag": np.bool_(True)})
    assert out == {"flag": True}
    assert isinstance(out["flag"], bool)


def test_numpy_integer_converted():
    out = sanitize_for_json({"n": np.int64(7)})
    assert out["n"] == 7
    assert isinstance(out["n"], int)


def test_numpy_float_converted():
    out = sanitize_for_json({"v": np.float64(3.14)})
    assert isinstance(out["v"], float)
    assert abs(out["v"] - 3.14) < 1e-9


def test_numpy_array_converted_to_list():
    out = sanitize_for_json(np.array([1, 2, 3]))
    assert out == [1, 2, 3]


def test_nested_structure():
    payload = {
        "a": [np.int64(1), np.float64(2.5), {"deep": np.bool_(False)}],
        "b": np.array([1.5, 2.5]),
    }
    out = sanitize_for_json(payload)
    s = json.dumps(out)  # 직렬화 가능해야 함
    parsed = json.loads(s)
    assert parsed["a"][0] == 1
    assert parsed["a"][2]["deep"] is False
    assert parsed["b"] == [1.5, 2.5]


def test_passthrough_python_native():
    payload = {"x": 1, "y": "hello", "z": [1, 2]}
    assert sanitize_for_json(payload) == payload
