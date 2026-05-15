"""PC 고유 식별자 생성.

기존 agent.py의 _get_fixed_pc_id() 로직을 모듈화.
- MAC 주소 기반 고정 ID (재시작에도 변하지 않음)
- 멀티캐스트 비트 검출 시 hostname 폴백
"""
from __future__ import annotations

import socket
import uuid


def get_fixed_pc_id() -> str:
    """MAC 기반 12자 hex 또는 hostname 기반 16자 ID."""
    try:
        mac = uuid.getnode()
        # uuid.getnode()는 실제 MAC을 못 얻으면 멀티캐스트 비트(40)를 세팅한 임의값을 반환.
        if (mac >> 40) & 1:
            raise ValueError("no real MAC")
        return format(mac, "012x")[:12]
    except Exception:
        return socket.gethostname()[:16].replace(" ", "_")


# 모듈 임포트 시 1회만 계산
PC_ID: str = get_fixed_pc_id()
