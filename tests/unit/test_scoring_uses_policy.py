"""verdict_classifier 와 indicator_calculator 가 정책 값을 사용함을 확인."""
import pytest

from ml_server.policy import reload_policies, get_scoring_policy
from ml_server.policy import loader as policy_loader
from ml_server.scorer.verdict_classifier import classify_verdict


@pytest.fixture
def custom_policy_dir(tmp_path, monkeypatch):
    (tmp_path / "scoring_policy.yaml").write_text(
        "version: 'test-1'\n"
        "thresholds: {observe: 100, suspicious: 200, high_risk: 300}\n"
        "limits: {ml_score_cap: 2, max_context_discount: -4, danger_override_max_discount: -1}\n"
        "scores: {a: 1}\n"
        "context_discounts: {startup: -1, class_or_free: -1}\n",
        encoding="utf-8",
    )
    (tmp_path / "allowlist.yaml").write_text(
        "version: 'test-1'\n"
        "whitelist_processes: []\n"
        "game_render_processes: []\n"
        "compile_encode_processes: []\n"
        "mining_processes: []\n"
        "mining_pool_ip_prefixes: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RADA_POLICY_DIR", str(tmp_path))
    reload_policies()
    yield
    monkeypatch.delenv("RADA_POLICY_DIR", raising=False)
    reload_policies()


def test_classify_uses_policy_thresholds(custom_policy_dir):
    # 14는 더 이상 high_risk가 아님 (override=300)
    v, _ = classify_verdict(final_score=14.0, process_score=0)
    assert v == "NORMAL"
    v, _ = classify_verdict(final_score=100.0, process_score=0)
    assert v == "OBSERVE"
    v, _ = classify_verdict(final_score=200.0, process_score=0)
    assert v == "SUSPICIOUS"
    v, _ = classify_verdict(final_score=300.0, process_score=0)
    assert v == "HIGH_RISK"


def test_default_policy_thresholds_match_legacy():
    reload_policies()
    th = get_scoring_policy().thresholds
    assert th.observe == 5
    assert th.suspicious == 9
    assert th.high_risk == 14
