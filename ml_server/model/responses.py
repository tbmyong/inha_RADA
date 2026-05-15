"""응답 모델 (Spring Boot 페이로드 호환 — 키 변경 금지)."""
from pydantic import BaseModel
from typing import Literal


class AgentJudgment(BaseModel):
    """AI Agent 판단 응답 스키마.

    실제 응답은 dict 그대로 반환되지만, 출력 스키마 검증/문서화용.
    """
    judgment: Literal["NORMAL", "SUSPICIOUS", "DANGEROUS"]
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    reason:   str
    action:   str
    hw_degradation: Literal["NONE", "SUSPECTED", "CONFIRMED"]
    is_mock:  bool
