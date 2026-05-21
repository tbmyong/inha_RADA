"""user_idle_ms collector unit tests.

Windows 외 OS 에서도 동작해야 하므로 platform branching 가드를 검증한다.
"""
from __future__ import annotations

import platform

import pytest

from client_core.collector import system_idle


def test_collect_returns_tuple():
    idle_ms, reason = system_idle.collect()
    # 둘 중 정확히 하나만 None — XOR
    assert (idle_ms is None) != (reason is None)


def test_collect_idle_ms_is_non_negative_when_present():
    idle_ms, reason = system_idle.collect()
    if idle_ms is not None:
        assert idle_ms >= 0
        assert isinstance(idle_ms, int)


def test_non_windows_returns_missing_reason():
    # 강제로 init reason 을 비-Windows 로 만들어서 missing 경로 검증
    original = system_idle._INIT_REASON
    try:
        system_idle._set_init_reason_for_test("non_windows_os")
        idle_ms, reason = system_idle.collect()
        assert idle_ms is None
        assert reason == "non_windows_os"
    finally:
        system_idle._set_init_reason_for_test(original)


def test_runtime_error_path_returns_reason():
    # init 은 성공했다고 가정 (current platform 에 따라 다를 수 있음).
    # missing reason 형식 확인용 — non-None 일 때 string 이어야 한다.
    idle_ms, reason = system_idle.collect()
    if reason is not None:
        assert isinstance(reason, str)
        assert len(reason) > 0


@pytest.mark.skipif(platform.system() != "Windows", reason="GetLastInputInfo is Windows-only")
def test_windows_idle_is_an_integer_ms():
    """Windows 호스트에서 실제 idle_ms 가 정수 ms 로 나오는지 확인."""
    idle_ms, reason = system_idle.collect()
    assert reason is None, f"unexpected missing reason on Windows: {reason}"
    assert isinstance(idle_ms, int)
    # 일반적으로 0 ~ 수초 범위 (테스트 직전에 키보드 활동했음)
    # 절대값 검증보단 상식 범위 (49.7일 미만)
    assert idle_ms < 49 * 24 * 3600 * 1000
