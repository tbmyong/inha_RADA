"""Layer1 알람 dataclass."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Alert:
    type: str
    severity: str  # HIGH / MEDIUM / LOW
    detail: str
    layer: Optional[int] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # layer가 None이면 키를 제거 (기존 absolute_breach 형식 유지)
        if d.get("layer") is None:
            d.pop("layer", None)
        return d
