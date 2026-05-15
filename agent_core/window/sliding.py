"""고정 길이 슬라이딩 윈도우 (deque 래퍼)."""
from __future__ import annotations

from collections import deque
from typing import Iterable, Iterator, List


class SlidingWindow:
    """고정 maxlen deque에 임의 dict 스냅샷을 누적.

    - 단기 윈도우 (LOCAL_WINDOW_SIZE=36): 패턴 분석용
    - 장기 기저선 (HW_BASELINE_WINDOW=360): 노후화 추적용
    """

    def __init__(self, max_size: int) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self._max_size = max_size
        self._buf: deque = deque(maxlen=max_size)

    @property
    def max_size(self) -> int:
        return self._max_size

    def append(self, item) -> None:
        self._buf.append(item)

    def extend(self, items: Iterable) -> None:
        self._buf.extend(items)

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self) -> Iterator:
        return iter(self._buf)

    def __getitem__(self, idx):
        return list(self._buf)[idx]

    def to_list(self) -> List:
        return list(self._buf)

    def is_full(self) -> bool:
        return len(self._buf) >= self._max_size

    def clear(self) -> None:
        self._buf.clear()
