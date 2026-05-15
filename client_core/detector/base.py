"""Detector 베이스 - detect()는 alert dict의 list를 반환."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, *args, **kwargs) -> List[dict]:
        ...
