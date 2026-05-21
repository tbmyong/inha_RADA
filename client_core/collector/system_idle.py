"""사용자 idle 시간 수집기.

목적
----
KT cloud / INESC-ID NCA 2020 / PMC11623100 등 cryptojacking 탐지 자료에서 공통적으로
강조되는 **"사용자가 비활동 상태인데도 자원이 풀가동되는 패턴"** 을 잡기 위한 신호.

API
---
Windows: ``user32.GetLastInputInfo`` + ``kernel32.GetTickCount`` 로 마지막 키보드/마우스
입력 이후 경과 ms 를 계산. 일반 사용자 권한으로 호출 가능, 호출당 ~1µs.

다른 OS (Linux/macOS) 는 본 프로젝트 운영 대상 외 — 일단 ``None`` 으로 처리하고
``user_idle_collection_missing_reason`` 으로 사유를 노출 (F5 의 missing-vs-zero 패턴 준수).

제약
----
- Windows console 세션 한정. RDP/원격 세션에선 console 의 마지막 입력만 추적.
- 화면 잠금 시 입력 timestamp 가 잠금 시점에 고정 → idle 은 계속 증가 (mining 탐지엔
  오히려 유리).
- 키 내용/마우스 좌표는 수집하지 않음 — 단순 "마지막 입력 이후 경과 시간" 만.
"""
from __future__ import annotations

import logging
import platform
from typing import Optional, Tuple

log = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"

# 모듈 로드 시 ctypes / Windows API 준비. 실패하면 _INIT_REASON 에 기록하고
# 이후 collect() 는 None + reason 만 반환.
_INIT_REASON: Optional[str] = None
_GET_LAST_INPUT_INFO = None
_GET_TICK_COUNT = None
_LASTINPUTINFO_CLS = None


def _init_windows_api() -> None:
    global _GET_LAST_INPUT_INFO, _GET_TICK_COUNT, _LASTINPUTINFO_CLS, _INIT_REASON
    if not _IS_WINDOWS:
        _INIT_REASON = "non_windows_os"
        return
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("dwTime", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
        user32.GetLastInputInfo.restype = wintypes.BOOL
        kernel32.GetTickCount.restype = wintypes.DWORD

        _GET_LAST_INPUT_INFO = user32.GetLastInputInfo
        _GET_TICK_COUNT = kernel32.GetTickCount
        _LASTINPUTINFO_CLS = LASTINPUTINFO
    except Exception as exc:  # pragma: no cover - depends on host OS
        _INIT_REASON = f"win_api_init_failed:{type(exc).__name__}"
        log.warning("GetLastInputInfo init failed: %s", exc)


_init_windows_api()


def collect() -> Tuple[Optional[int], Optional[str]]:
    """사용자 idle 시간 (ms) 과 수집 실패 사유 (있으면) 를 반환.

    Returns
    -------
    (idle_ms, missing_reason)
        idle_ms 가 None 이면 missing_reason 에 사유. 둘 다 동시에 의미 있을 수는 없다.
    """
    if _INIT_REASON is not None:
        return None, _INIT_REASON
    if _GET_LAST_INPUT_INFO is None or _GET_TICK_COUNT is None or _LASTINPUTINFO_CLS is None:
        return None, "uninitialised"
    try:
        import ctypes

        lii = _LASTINPUTINFO_CLS()
        lii.cbSize = ctypes.sizeof(lii)
        ok = _GET_LAST_INPUT_INFO(ctypes.byref(lii))
        if not ok:
            return None, "get_last_input_info_failed"
        # DWORD wrap-around (~49.7 일) 안전 처리:
        tick = _GET_TICK_COUNT()
        idle_ms = (tick - lii.dwTime) & 0xFFFFFFFF
        return int(idle_ms), None
    except Exception as exc:  # pragma: no cover
        return None, f"runtime_error:{type(exc).__name__}"


# ---- 테스트용 helper (단위 테스트가 사용; 운영 코드는 사용 안 함) -------------
def _set_init_reason_for_test(reason: Optional[str]) -> None:
    """테스트 전용. 강제로 init reason 을 바꿔서 missing 경로 검증."""
    global _INIT_REASON
    _INIT_REASON = reason
