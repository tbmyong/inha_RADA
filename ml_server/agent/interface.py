"""AI Agent 인터페이스 — Claude API와 Mock이 동일 스키마를 출력하도록 강제."""
from typing import Protocol, Dict, Any
from ..model.requests import MetricsRequest


class AgentInterface(Protocol):
    """judge() 응답 스키마:
        {"judgment": "NORMAL|SUSPICIOUS|DANGEROUS",
         "severity": "LOW|MEDIUM|HIGH",
         "reason":   str,
         "action":   str,
         "hw_degradation": "NONE|SUSPECTED|CONFIRMED"}
    """

    def judge(self, metrics: MetricsRequest, pattern_result: Dict[str, Any],
              global_hw: Dict[str, Any]) -> Dict[str, Any]: ...
