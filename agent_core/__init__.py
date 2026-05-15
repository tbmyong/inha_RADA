"""agent_core: 모니터링 에이전트 모듈화 패키지.

기존 agent.py의 단일 파일 구조를 책임 단위로 분리.
- config: 설정 로딩/기본값
- identity: PC 고유 식별
- timeslot: 시간대 슬롯 판정
- collector: psutil/GPU 등 메트릭 수집
- window: 슬라이딩 윈도우
- detector: Layer1 규칙 기반 탐지
- sender: ML 서버 전송 + 로컬 큐
- model: 페이로드/알람 dataclass
- runtime: 메인 루프 오케스트레이션
"""

__version__ = "9.0.0"
