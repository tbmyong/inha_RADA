"""is_mock 필드 — runner Claude/Mock 분기 회귀."""
import pytest

from ml_server.agent import runner
from ml_server.model.requests import MetricsRequest


def _metrics() -> MetricsRequest:
    return MetricsRequest(
        pc_id="pc-mock-1",
        timestamp="2026-05-13T10:00:00",
        cpu_percent=20.0,
        memory_percent=40.0,
        inbound_mb=0.0,
        outbound_mb=0.0,
        external_packet_count=0,
    )


def _pattern():
    return {"verdict": "NORMAL", "scores": {"final": 0.0},
            "signals": {}, "alerts": []}


def test_claude_success_is_mock_false(monkeypatch):
    monkeypatch.setattr(runner, "USE_REAL_CLAUDE", True)
    monkeypatch.setattr(runner, "call_claude_api",
                        lambda prompt: {"judgment": "NORMAL", "severity": "LOW",
                                        "reason": "ok", "action": "none",
                                        "hw_degradation": "NONE"})
    monkeypatch.setattr(runner, "build_prompt", lambda m, p, g: "prompt")

    out = runner.run_ai_agent(_metrics(), _pattern(), {"detected": False})
    assert out["is_mock"] is False
    assert out["judgment"] == "NORMAL"


def test_claude_failure_fallback_is_mock_true(monkeypatch):
    monkeypatch.setattr(runner, "USE_REAL_CLAUDE", True)

    def _boom(_):
        raise RuntimeError("api down")

    monkeypatch.setattr(runner, "call_claude_api", _boom)
    monkeypatch.setattr(runner, "build_prompt", lambda m, p, g: "prompt")

    out = runner.run_ai_agent(_metrics(), _pattern(), {"detected": False})
    assert out["is_mock"] is True
    # Mock 스키마 충족 확인
    assert "judgment" in out and "severity" in out


def test_mock_only_is_mock_true(monkeypatch):
    monkeypatch.setattr(runner, "USE_REAL_CLAUDE", False)
    # config 기반 분기도 Mock 강제
    monkeypatch.setattr(runner.config, "use_real_claude", lambda: False)

    out = runner.run_ai_agent(_metrics(), _pattern(), {"detected": False})
    assert out["is_mock"] is True
