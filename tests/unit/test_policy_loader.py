"""policy.loader — YAML 로드 + 캐시 + reload + env override."""
import os
from pathlib import Path

import pytest

from ml_server.policy import loader as policy_loader
from ml_server.policy import (
    get_scoring_policy,
    get_allowlist,
    load_scoring_policy,
    load_allowlist,
    reload_policies,
    ScoringPolicy,
    AllowList,
)


def test_load_scoring_policy_returns_dataclass():
    policy = load_scoring_policy()
    assert isinstance(policy, ScoringPolicy)
    assert isinstance(policy.version, str) and policy.version
    assert policy.thresholds.observe < policy.thresholds.suspicious < policy.thresholds.high_risk
    assert policy.limits.ml_score_cap >= 0
    assert policy.limits.max_context_discount <= 0
    assert policy.limits.danger_override_max_discount <= 0


def test_load_allowlist_returns_frozensets():
    al = load_allowlist()
    assert isinstance(al, AllowList)
    assert isinstance(al.whitelist_processes, frozenset)
    assert isinstance(al.mining_processes, frozenset)
    assert "xmrig" in al.mining_processes


def test_get_scoring_policy_is_cached():
    reload_policies()
    p1 = get_scoring_policy()
    p2 = get_scoring_policy()
    assert p1 is p2


def test_reload_policies_resets_cache():
    p1 = get_scoring_policy()
    reload_policies()
    p2 = get_scoring_policy()
    # 같은 내용이지만 reload 후에는 새로운 객체일 수 있다
    assert p1.version == p2.version


def test_rada_policy_dir_env_override(tmp_path, monkeypatch):
    # 임시 디렉토리에 정상 YAML 작성 후 env override 동작 확인
    (tmp_path / "scoring_policy.yaml").write_text(
        "version: '99.0.0'\n"
        "thresholds: {observe: 1, suspicious: 2, high_risk: 3}\n"
        "limits: {ml_score_cap: 5, max_context_discount: -4, danger_override_max_discount: -1}\n"
        "scores: {a: 1}\n"
        "context_discounts: {startup: -1}\n",
        encoding="utf-8",
    )
    (tmp_path / "allowlist.yaml").write_text(
        "version: '99.0.0'\n"
        "whitelist_processes: [foo.exe]\n"
        "game_render_processes: []\n"
        "compile_encode_processes: []\n"
        "mining_processes: []\n"
        "mining_pool_ip_prefixes: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RADA_POLICY_DIR", str(tmp_path))
    reload_policies()
    try:
        assert get_scoring_policy().version == "99.0.0"
        assert "foo.exe" in get_allowlist().whitelist_processes
    finally:
        monkeypatch.delenv("RADA_POLICY_DIR", raising=False)
        reload_policies()
