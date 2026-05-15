"""danger override — 위험신호 1개라도 True 시 discount ≥ -1 로 클램프."""
from collections import deque

from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest


def _metrics(**overrides):
    base = dict(
        pc_id="pc-danger", timestamp="2026-05-04T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )
    base.update(overrides)
    return MetricsRequest(**base)


def _seed_history(outbound_mean=0.05):
    h = deque()
    for _ in range(15):
        h.append({
            "cpu_percent": 10, "gpu_percent": 5, "gpu_vram_mb": 100,
            "gpu_power_w": 30, "inbound_mb": 0.0, "outbound_mb": outbound_mean,
            "external_packet_count": 1, "top_processes": [],
        })
    return h


def test_unknown_process_plus_net_out_sustained_overrides_discount():
    history = _seed_history()
    m = _metrics(
        outbound_mb=2.0,  # net_out_sustained True
        top_processes=[{
            "name": "unknown.exe", "cpu_percent": 80.0,
            "memory_percent": 10.0, "path": "C:\\Users\\foo\\app\\unknown.exe",
        }],
        local_alerts=[
            {"type": "STARTUP", "severity": "LOW", "detail": ""},
            {"type": "SECURITY_SCAN", "severity": "LOW", "detail": ""},
            {"type": "MAINTENANCE_UPDATE", "severity": "LOW", "detail": ""},
            {"type": "LAB_AGENT", "severity": "LOW", "detail": ""},
        ],
    )
    result = analyze_pattern(m, history, slot="class")
    sb = result["scores"]["score_breakdown"]
    # 정황 -6 클램프 -4 → danger override → -1
    assert sb["context_discount"] == -1
    assert result["scores"]["context_discount_clamped"] is True


def test_mining_process_overrides_discount():
    m = _metrics(
        top_processes=[{
            "name": "xmrig.exe", "cpu_percent": 90,
            "memory_percent": 5, "path": "C:\\x\\xmrig.exe",
        }],
        local_alerts=[
            {"type": "SECURITY_SCAN", "severity": "LOW", "detail": ""},
            {"type": "MAINTENANCE_UPDATE", "severity": "LOW", "detail": ""},
        ],
    )
    result = analyze_pattern(m, deque(), slot="class")
    sb = result["scores"]["score_breakdown"]
    assert sb["context_discount"] >= -1
