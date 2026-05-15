"""ML 서버 페이로드 키 정의 + 검증.

ML 서버는 정확히 22개의 키를 기대한다 (보존 필수).
선택적 derived_features 키는 ML 서버가 점수에 사용하지 않으며,
하위 호환을 위해 ALL_PAYLOAD_KEYS 에서만 추가된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

# ML 서버 페이로드 키 22개 (불변)
ML_PAYLOAD_KEYS: List[str] = [
    "pc_id",
    "timestamp",
    "cpu_percent",
    "cpu_core_count",
    "memory_percent",
    "memory_used_gb",
    "memory_total_gb",
    "disk_read_mb",
    "disk_write_mb",
    "inbound_mb",
    "outbound_mb",
    "inbound_total_mb",
    "outbound_total_mb",
    "external_packet_count",
    "external_connection_count",
    "external_connections",
    "active_ports",
    "gpu",
    "top_processes",
    "loop_elapsed",
    "local_alerts",
    "boxplot_signal",
]

# 선택 키 (수신/저장만; 점수 무영향)
OPTIONAL_PAYLOAD_KEYS: List[str] = [
    "derived_features",
]

# 전체 (확장된) 키 — 회귀 검증용
ALL_PAYLOAD_KEYS: List[str] = ML_PAYLOAD_KEYS + OPTIONAL_PAYLOAD_KEYS


@dataclass
class MetricsPayload:
    """문서화/타입체크 용도. 실제 송신은 dict로 진행."""

    pc_id: str
    timestamp: str

    @staticmethod
    def keys() -> List[str]:
        return list(ML_PAYLOAD_KEYS)

    @staticmethod
    def validate(payload: dict) -> List[str]:
        """missing_keys 리스트 반환. 비어있으면 정상 (22키 필수만)."""
        return [k for k in ML_PAYLOAD_KEYS if k not in payload]

    @staticmethod
    def validate_extended(payload: dict) -> List[str]:
        """확장 키 (derived_features 등) 누락에 대한 경고용 (필수 아님).

        반환된 리스트는 경고 대상이며, 호출자는 예외를 던지지 않아야 한다.
        """
        return [k for k in OPTIONAL_PAYLOAD_KEYS if k not in payload]
