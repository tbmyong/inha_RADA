"""score_breakdown 정확 분류 — 8키 구조 + 값 의미 검증."""
from collections import deque

from ml_server.scorer.verdict_classifier import analyze_pattern
from ml_server.model.requests import MetricsRequest

EXPECTED_KEYS = {
    "resource", "network", "process", "episode",
    "correlation", "ml", "context_discount", "final",
}


def _metrics(**overrides):
    base = dict(
        pc_id="pc-sb8", timestamp="2026-05-04T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )
    base.update(overrides)
    return MetricsRequest(**base)


def test_keys_exact_match():
    r = analyze_pattern(_metrics(), deque(), slot="class")
    assert EXPECTED_KEYS.issubset(set(r["scores"]["score_breakdown"].keys()))


def test_resource_grows_with_cpu_high():
    r0 = analyze_pattern(_metrics(cpu_percent=10), deque(), slot="class")
    r1 = analyze_pattern(_metrics(cpu_percent=99, memory_percent=92), deque(), slot="class")
    assert r1["scores"]["score_breakdown"]["resource"] > r0["scores"]["score_breakdown"]["resource"]


def test_process_breakdown_picks_known_miner():
    m = _metrics(top_processes=[
        {"name": "xmrig.exe", "cpu_percent": 95, "memory_percent": 5,
         "path": "C:\\x\\xmrig.exe"}
    ])
    r = analyze_pattern(m, deque(), slot="class")
    assert r["scores"]["score_breakdown"]["process"] >= 10


def test_final_matches_scores_final():
    r = analyze_pattern(_metrics(), deque(), slot="class")
    sb = r["scores"]["score_breakdown"]
    assert sb["final"] == r["scores"]["final"]
