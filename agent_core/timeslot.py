"""시간대 슬롯 판정.

평일 9~18시는 'class', 그 외/주말은 'free'.
agent.py의 get_time_slot() 로직과 1:1 매칭.
"""
from __future__ import annotations

import datetime
from typing import Optional


def get_time_slot(now: Optional[datetime.datetime] = None) -> str:
    """현재 시간대 슬롯 반환. 인자 주입은 테스트용."""
    now = now or datetime.datetime.now()
    weekday = now.weekday()
    hour = now.hour
    if weekday >= 5:
        return "free"
    if 9 <= hour < 18:
        return "class"
    return "free"


__all__ = ["get_time_slot"]
