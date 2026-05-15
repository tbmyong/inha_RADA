"""spike_count_1m 단독 신호 → network 카테고리 0점.

동반 조건이 1개라도 있으면 network 가산.
"""
from collections import deque

from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest


def _metrics(**overrides):
    base = dict(
        pc_id="pc-spike", timestamp="2026-05-04T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0,
        external_packet_count=20,  # spike alone (≥ 8)
    )
    base.update(overrides)
    return MetricsRequest(**base)


def test_spike_alone_yields_zero_network():
    result = analyze_pattern(_metrics(), deque(), slot="class")
    assert result["scores"]["score_breakdown"]["network"] == 0


def test_spike_with_one_companion_yields_positive_network():
    # disk_write + outbound_mb 충분 → net_out_sustained 컴패니언 + spike
    # history 없어도 outbound_spike 가능
    history = deque()
    # 적당한 outbound spike 만들기 위해 history 시드
    for _ in range(15):
        history.append({
            "cpu_percent": 10, "gpu_percent": 5, "gpu_vram_mb": 100,
            "gpu_power_w": 30, "inbound_mb": 0.0, "outbound_mb": 0.05,
            "external_packet_count": 1, "top_processes": [],
        })
    m = _metrics(outbound_mb=2.0, disk_write_mb=3.0)
    result = analyze_pattern(m, history, slot="class")
    assert result["scores"]["score_breakdown"]["network"] > 0
