"""F5 — ProcessCollector last_missing_reason 속성 검증.

예외 시에만 reason 채워지고, 정상 시(빈 리스트라도) None 이어야 한다.
"""
from __future__ import annotations

from unittest.mock import patch

from client_core.collector.process import ProcessCollector


def test_attribute_exists_and_starts_none():
    pc = ProcessCollector()
    assert hasattr(pc, "last_missing_reason")
    # __init__ 직후
    assert pc.last_missing_reason is None


def test_success_clears_reason():
    pc = ProcessCollector(top_n=3)
    pc.last_missing_reason = "stale"
    pc.collect()
    assert pc.last_missing_reason is None


def test_permission_error_sets_reason():
    pc = ProcessCollector()
    with patch(
        "client_core.collector.process.psutil.process_iter",
        side_effect=PermissionError("denied"),
    ):
        out = pc.collect()
    assert out == []
    assert pc.last_missing_reason == "permission_error"


def test_os_error_sets_reason():
    pc = ProcessCollector()
    with patch(
        "client_core.collector.process.psutil.process_iter",
        side_effect=OSError("oops"),
    ):
        out = pc.collect()
    assert out == []
    assert pc.last_missing_reason == "os_error"


def test_unknown_exception_sets_reason():
    pc = ProcessCollector()
    with patch(
        "client_core.collector.process.psutil.process_iter",
        side_effect=RuntimeError("?"),
    ):
        out = pc.collect()
    assert out == []
    assert pc.last_missing_reason == "unknown"
