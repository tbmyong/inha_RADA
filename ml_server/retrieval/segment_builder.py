"""Sliding window snapshot -> segment dict.

최근 N개의 snapshot 을 모아 시계열 segment 한 묶음을 만든다.
MVP 는 1분(=12 snapshot @ 5초) 윈도우.
"""
from __future__ import annotations
from collections import deque
from typing import Optional, Iterable


def build_segment(
    pc_id: str,
    slot: str,
    history: Iterable[dict],
    window_size: int = 12,
) -> Optional[dict]:
    """최근 window_size 개 snapshot 으로 segment 생성. 부족하면 None."""
    if history is None:
        return None
    if isinstance(history, deque):
        snaps = list(history)
    else:
        snaps = list(history)
    if len(snaps) < window_size:
        return None
    snaps = snaps[-window_size:]
    start_ts = snaps[0].get("timestamp") or ""
    end_ts = snaps[-1].get("timestamp") or ""
    return {
        "segment_id": f"{pc_id}:{slot}:{start_ts}",
        "pc_id": pc_id,
        "slot": slot,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "window_size": window_size,
        "snapshots": snaps,
    }
