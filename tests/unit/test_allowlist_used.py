"""signal_extractor 가 YAML allowlist 를 사용함을 확인."""
import pytest
from collections import deque

from ml_server.policy import reload_policies
from ml_server.scorer.signal_extractor import _effective_whitelist, extract_signals
from ml_server.model.requests import MetricsRequest


def test_effective_whitelist_includes_yaml_entries():
    reload_policies()
    wl = _effective_whitelist()
    # YAML 정의 + 기존 config 정의 모두 포함
    assert "python.exe" in wl
    assert "chrome.exe" in wl
    assert "explorer.exe" in wl


def test_effective_whitelist_union_with_custom(tmp_path, monkeypatch):
    (tmp_path / "scoring_policy.yaml").write_text(
        "version: 'al-1'\n"
        "thresholds: {observe: 5, suspicious: 9, high_risk: 14}\n"
        "limits: {ml_score_cap: 5, max_context_discount: -4, danger_override_max_discount: -1}\n"
        "scores: {}\n"
        "context_discounts: {}\n",
        encoding="utf-8",
    )
    (tmp_path / "allowlist.yaml").write_text(
        "version: 'al-1'\n"
        "whitelist_processes: ['my-special-proc.exe']\n"
        "game_render_processes: []\n"
        "compile_encode_processes: []\n"
        "mining_processes: []\n"
        "mining_pool_ip_prefixes: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RADA_POLICY_DIR", str(tmp_path))
    reload_policies()
    try:
        wl = _effective_whitelist()
        assert "my-special-proc.exe" in wl
        # 기존 config 도 여전히 포함
        assert "python.exe" in wl
    finally:
        monkeypatch.delenv("RADA_POLICY_DIR", raising=False)
        reload_policies()


def test_unknown_process_active_respects_whitelist():
    """allowlist 의 프로세스는 unknown_process_active를 트리거하지 않음."""
    reload_policies()
    m = MetricsRequest(
        pc_id="pc-al", timestamp="2026-05-04T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
        top_processes=[{"name": "chrome.exe", "cpu_percent": 80.0, "path": ""}],
    )
    sig = extract_signals(m, deque(), slot="class")
    assert sig["signals"]["unknown_process_active"] is False
