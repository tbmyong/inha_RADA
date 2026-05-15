"""correlation 카테고리 — 동시 발생 신호 가산.

- disk_write + net_out_sustained → +5
- unknown_process + net_out_sustained → +5
- appdata_exec + net_out_sustained → +6
- known_miner → +10
"""
from collections import deque

from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest


def _metrics(**overrides):
    base = dict(
        pc_id="pc-corr", timestamp="2026-05-04T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )
    base.update(overrides)
    return MetricsRequest(**base)


def _seed_history():
    h = deque()
    for _ in range(15):
        h.append({
            "cpu_percent": 10, "gpu_percent": 5, "gpu_vram_mb": 100,
            "gpu_power_w": 30, "inbound_mb": 0.0, "outbound_mb": 0.05,
            "external_packet_count": 1, "top_processes": [],
        })
    return h


def test_disk_write_net_out_correlation_plus_5():
    h = _seed_history()
    m = _metrics(disk_write_mb=5.0, outbound_mb=3.0)
    r = analyze_pattern(m, h, slot="class")
    assert r["scores"]["score_breakdown"]["correlation"] >= 5


def test_unknown_process_net_out_correlation_plus_5():
    h = _seed_history()
    m = _metrics(
        outbound_mb=2.0,
        top_processes=[{"name": "weird.exe", "cpu_percent": 70,
                        "memory_percent": 5, "path": "C:\\misc\\weird.exe"}],
    )
    r = analyze_pattern(m, h, slot="class")
    assert r["scores"]["score_breakdown"]["correlation"] >= 5


def test_known_miner_correlation_plus_10():
    m = _metrics(top_processes=[
        {"name": "xmrig.exe", "cpu_percent": 95, "memory_percent": 5,
         "path": "C:\\x\\xmrig.exe"}
    ])
    r = analyze_pattern(m, deque(), slot="class")
    assert r["scores"]["score_breakdown"]["correlation"] >= 10


def test_no_correlation_in_quiet_state():
    r = analyze_pattern(_metrics(), deque(), slot="class")
    assert r["scores"]["score_breakdown"]["correlation"] == 0
