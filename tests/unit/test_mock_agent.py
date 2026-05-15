"""Mock agent 출력 스키마 — Claude API와 동일."""
from ml_server.agent.mock_agent import mock_agent_judgment
from ml_server.model.requests import MetricsRequest

REQUIRED_KEYS = {"judgment", "severity", "reason", "action", "hw_degradation"}
JUDGMENT_VALS = {"NORMAL", "SUSPICIOUS", "DANGEROUS"}
SEVERITY_VALS = {"LOW", "MEDIUM", "HIGH"}
HW_VALS       = {"NONE", "SUSPECTED", "CONFIRMED"}


def make_metrics(**overrides):
    base = dict(
        pc_id="pc-1", timestamp="2026-05-05T10:00:00",
        cpu_percent=20.0, memory_percent=40.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )
    base.update(overrides)
    return MetricsRequest(**base)


def _check_schema(out: dict):
    assert REQUIRED_KEYS.issubset(out.keys())
    assert out["judgment"] in JUDGMENT_VALS
    assert out["severity"] in SEVERITY_VALS
    assert out["hw_degradation"] in HW_VALS
    assert isinstance(out["reason"], str) and out["reason"]
    assert isinstance(out["action"], str) and out["action"]


def test_normal_verdict_returns_valid_schema():
    metrics = make_metrics()
    pattern = {"verdict": "NORMAL", "scores": {"final": 0.0},
               "signals": {}, "alerts": []}
    out = mock_agent_judgment(metrics, pattern, {"detected": False})
    _check_schema(out)
    assert out["judgment"] == "NORMAL"


def test_confirmed_mining_alert_returns_dangerous_high():
    """CONFIRMED_MINING은 verdict가 아닌 alerts[0].type으로 표현 (HIGH_RISK 통합)."""
    metrics = make_metrics()
    pattern = {"verdict": "HIGH_RISK",
               "scores": {"process": 10, "final": 14.0},
               "signals": {"mining_pool_ip": True},
               "alerts": [{"type": "CONFIRMED_MINING", "severity": "HIGH",
                           "detail": "채굴 프로세스 감지", "score": 14.0}]}
    out = mock_agent_judgment(metrics, pattern, {"detected": False})
    _check_schema(out)
    assert out["judgment"] == "DANGEROUS"
    assert out["severity"] == "HIGH"
    # 후보 표현으로 변경 확인
    assert "채굴 의심" in out["reason"]
    assert "확인이 필요" in out["reason"]
    assert "가능성" in out["reason"]


def test_observe_verdict_branch():
    """LOW_RISK 잔존 없음 — OBSERVE 분기 동작 확인."""
    metrics = make_metrics()
    pattern = {"verdict": "OBSERVE", "scores": {"final": 5.0},
               "signals": {}, "alerts": []}
    out = mock_agent_judgment(metrics, pattern, {"detected": False})
    _check_schema(out)
    assert out["judgment"] == "SUSPICIOUS"
    assert out["severity"] == "LOW"


def test_high_mem_low_cpu_uses_candidate_phrase():
    """메모리 임계 + CPU 낮음 분기에서 '비인가 고부하 작업 가능성' 후보 표현 사용."""
    metrics = make_metrics(cpu_percent=10.0, memory_percent=97.0)
    pattern = {"verdict": "NORMAL", "scores": {"final": 0.0},
               "signals": {}, "alerts": [
                   {"type": "LOCAL_MEM_HIGH", "severity": "HIGH", "detail": "mem high"},
               ]}
    out = mock_agent_judgment(metrics, pattern, {"detected": False})
    _check_schema(out)
    assert "비인가 고부하 작업 가능성" in out["reason"]


def test_no_forbidden_definitive_phrases():
    """확정 표현이 reason에 등장하지 않아야 한다."""
    metrics = make_metrics(cpu_percent=10.0, memory_percent=97.0)
    cases = [
        ({"verdict": "HIGH_RISK",
          "scores": {"process": 10, "final": 14.0},
          "signals": {"mining_pool_ip": True},
          "alerts": [{"type": "CONFIRMED_MINING", "severity": "HIGH",
                      "detail": "miner", "score": 14.0}]},
         {"detected": False}),
        ({"verdict": "NORMAL", "scores": {"final": 0.0},
          "signals": {}, "alerts": [
              {"type": "LOCAL_MEM_HIGH", "severity": "HIGH", "detail": "mem high"}]},
         {"detected": False}),
    ]
    forbidden = ["EDR", "확실시", "오탐 제거", "정확한 악성코드", "악성코드 의심"]
    for pattern, gh in cases:
        result = mock_agent_judgment(metrics, pattern, gh)
        for word in forbidden:
            assert word not in result["reason"], (
                f"forbidden phrase '{word}' found in reason: {result['reason']}"
            )


def test_global_hw_detected_sets_suspected():
    metrics = make_metrics()
    pattern = {"verdict": "NORMAL", "scores": {"final": 0.0},
               "signals": {}, "alerts": []}
    out = mock_agent_judgment(metrics, pattern,
                              {"detected": True, "detail": "테스트 노후화"})
    _check_schema(out)
    # CONFIRMED 또는 SUSPECTED 둘 다 가능 (hw_status=CONFIRMED 후 노후화 분기)
    assert out["hw_degradation"] in {"SUSPECTED", "CONFIRMED"}
