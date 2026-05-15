"""정상 CSV-like 워크로드 회귀 — 평상시 trafic 만으로 SUSPICIOUS 이상이 뜨지 않아야 함.

idle/light CPU 사용 + 외부 패킷 약간 + 정상 프로세스 → verdict NORMAL/OBSERVE 이내.
"""
from collections import deque

from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest


def _normal(**overrides):
    base = dict(
        pc_id="pc-norm", timestamp="2026-05-04T10:00:00",
        cpu_percent=18.0, memory_percent=42.0,
        inbound_mb=0.05, outbound_mb=0.03,
        external_packet_count=2,
        top_processes=[
            {"name": "chrome.exe", "cpu_percent": 5,
             "memory_percent": 8, "path": "C:\\Program Files\\Chrome\\chrome.exe"},
        ],
    )
    base.update(overrides)
    return MetricsRequest(**base)


def test_idle_workload_yields_normal_or_observe():
    r = analyze_pattern(_normal(), deque(), slot="class")
    assert r["verdict"] in {"NORMAL", "OBSERVE"}


def test_idle_breakdown_components_small():
    r = analyze_pattern(_normal(), deque(), slot="class")
    sb = r["scores"]["score_breakdown"]
    assert sb["correlation"] == 0
    assert sb["process"] == 0
    assert sb["episode"] == 0
    # network 도 0 (spike 단독 제외 정책)
    assert sb["network"] == 0


def test_idle_final_below_observe_threshold():
    r = analyze_pattern(_normal(), deque(), slot="class")
    assert r["scores"]["final"] < 9  # SUSPICIOUS 임계 미만
