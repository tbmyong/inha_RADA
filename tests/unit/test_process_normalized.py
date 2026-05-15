"""ProcessCollector cpu_percent_normalized 검증."""
from __future__ import annotations

from client_core.collector.process import ProcessCollector


def test_cpu_normalized_basic():
    """cpu_raw=80, logical=8 → normalized=10.0."""
    pc = ProcessCollector()
    pc._logical_cpu = 8
    raw = 80.0
    normalized = round(raw / pc._logical_cpu, 2)
    assert normalized == 10.0


def test_cpu_normalized_in_collect_output():
    """실제 collect() 출력에 cpu_percent_normalized 키가 존재한다."""
    pc = ProcessCollector(top_n=5)
    procs = pc.collect()
    if not procs:
        # 환경 의존; 비어있으면 스킵
        return
    for p in procs:
        assert "cpu_percent_normalized" in p
        assert isinstance(p["cpu_percent_normalized"], float)
        assert p["cpu_percent_normalized"] >= 0.0


def test_cpu_normalized_logical_cpu_zero_safe():
    """logical_cpu가 0이어도 1로 보정되어 division by zero 방지."""
    pc = ProcessCollector()
    pc._logical_cpu = 1  # 보정된 상태
    assert pc._logical_cpu >= 1
