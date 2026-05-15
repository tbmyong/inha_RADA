"""Collector 추상 베이스."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseCollector(ABC):
    """모든 Collector는 collect()로 dict-like 결과를 반환한다."""

    @abstractmethod
    def collect(self) -> Any:
        ...
