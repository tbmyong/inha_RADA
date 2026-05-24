"""Mock vs Claude 분기 검증 — runner.py."""
from __future__ import annotations

import pytest

from ml_server.agent import runner

from .fixtures import seed_history, normal_metrics, anomaly_metrics

pytestmark = pytest.mark.integration


AGENT_KEYS = {"judgment", "severity", "reason", "action", "hw_degradation"}


def test_mock_agent_when_no_api_key(client, monkeypatch):
    """ANTHROPIC_API_KEY 미설정 → Mock agent 사용. agent dict 키 검증."""
    monkeypatch.setattr(runner, "USE_REAL_CLAUDE", False, raising=True)

    seed_history(client, pc_id="pc-AG1", slot="class", n=60)
    # P1-2: prime dos_spike streak so the assertion call fires the signal.
    payload = anomaly_metrics(pc_id="pc-AG1", slot="class", idx=300)
    client.post("/analyze", json=payload)
    r = client.post("/analyze", json=payload)
    body = r.json()
    assert body["agent"] is not None
    missing = AGENT_KEYS - set(body["agent"].keys())
    assert not missing, f"agent missing keys: {missing}"


def test_agent_skipped_on_normal(client, monkeypatch):
    """overall_severity == NORMAL 이면 agent 호출되지 않고 None."""
    monkeypatch.setattr(runner, "USE_REAL_CLAUDE", False, raising=True)

    r = client.post("/analyze",
                    json=normal_metrics(pc_id="pc-AG2", slot="class", idx=0))
    body = r.json()
    assert body["overall_severity"] == "NORMAL"
    assert body["agent"] is None


def test_claude_branch_invoked_when_enabled(client, monkeypatch):
    """USE_REAL_CLAUDE=True 일 때 call_claude_api 가 호출되어야 한다."""
    called = {"n": 0}

    def fake_call(prompt: str) -> dict:
        called["n"] += 1
        return {"judgment": "SUSPICIOUS", "severity": "HIGH",
                "reason": "테스트 가짜 응답.",
                "action": "테스트 권고.",
                "hw_degradation": "NONE"}

    monkeypatch.setattr(runner, "USE_REAL_CLAUDE", True, raising=True)
    monkeypatch.setattr(runner, "call_claude_api", fake_call, raising=True)

    seed_history(client, pc_id="pc-AG3", slot="class", n=60)
    # P1-2: prime dos_spike streak.
    payload = anomaly_metrics(pc_id="pc-AG3", slot="class", idx=300)
    client.post("/analyze", json=payload)
    r = client.post("/analyze", json=payload)
    body = r.json()
    assert called["n"] >= 1
    assert body["agent"]["judgment"] == "SUSPICIOUS"
