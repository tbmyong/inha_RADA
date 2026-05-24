"""기본 설정값. agent.py의 상수를 그대로 옮김."""
from typing import Dict, FrozenSet, Optional, Set

INTERVAL: int = 5
ML_SERVER_URL: str = "http://localhost:8000/analyze"
SPRING_BOOT_URL: str = "http://localhost:8080/api/metrics"

# 전송 모드: "mlserver" → ML 서버 직접, "springboot" → Spring Boot 메인 서버 경유
MODE: str = "springboot"
API_KEY: Optional[str] = None
VALID_MODES: FrozenSet[str] = frozenset({"mlserver", "springboot"})

LOCAL_WINDOW_SIZE: int = 36       # 5초 × 36 = 3분
HW_BASELINE_WINDOW: int = 360     # 5초 × 360 = 30분

# LocalQueue (sender/local_queue.py) 영속성 옵션
LOCAL_QUEUE_PATH: Optional[str] = None         # None = in-memory only
LOCAL_QUEUE_MAX_SIZE: int = 200
LOCAL_QUEUE_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB
LOCAL_QUEUE_FSYNC: bool = False

NORMAL_PORTS: Set[int] = {
    80, 443, 53, 123, 8443,
    5228, 5229, 5230,
    1935, 3478, 3479, 5349,
}

THRESHOLDS: Dict[str, dict] = {
    "class": {
        "cpu_warn":     85.0,
        "cpu_critical": 95.0,
        "mem_warn":     88.0,
        "mem_critical": 96.0,
        "gpu_warn":     85.0,
        "gpu_temp":     88.0,
    },
    "free": {
        "cpu_warn":     70.0,
        "cpu_critical": 85.0,
        "mem_warn":     80.0,
        "mem_critical": 92.0,
        "gpu_warn":     75.0,
        "gpu_temp":     85.0,
    },
}

ABSOLUTE_THRESHOLDS: dict = {
    "cpu_percent":  90.0,
    "mem_percent":  95.0,
    "gpu_percent":  90.0,
    "gpu_temp":     92.0,
    "disk_io_mbps": 500.0,
}

# HW degradation 발화 임계 — baseline 평균 대비 최근 평균의 비율.
# 이전 1.3 은 너무 민감해서 정상 dev burst (CPU baseline 15% → recent 21% = ratio 1.4)
# 도 모두 발화. 필드 측정에서 MEDIUM/NORMAL 404 건의 76% (308 건) 가 단일 신호
# LOCAL_HW_CPU_DEGRADATION 발화로 인한 false-positive 였다.
# 2.0 으로 강화하면 정상 burst 는 거의 통과하고, 실제 노후화/throttling
# (baseline 30% → recent 60%+ 같은) 패턴만 남는다.
HW_DEGRADATION_RATIO: float = 2.0
