"""AgentConfig mode 분기 / target_url / env override 단위 테스트."""
from __future__ import annotations

import pytest

from agent_core.config import defaults
from agent_core.config.loader import AgentConfig, _from_dict, load_config


def test_default_mode_is_springboot():
    cfg = AgentConfig()
    assert cfg.mode == "springboot"
    assert cfg.spring_boot_url == defaults.SPRING_BOOT_URL
    assert cfg.ml_server_url == defaults.ML_SERVER_URL
    assert cfg.api_key is None


def test_mlserver_mode_ok():
    cfg = AgentConfig(mode="mlserver")
    assert cfg.mode == "mlserver"


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        AgentConfig(mode="invalid")


def test_target_url_branches():
    sb = AgentConfig(mode="springboot",
                     spring_boot_url="http://sb:8080/api/metrics",
                     ml_server_url="http://ml:8000/analyze")
    ml = AgentConfig(mode="mlserver",
                     spring_boot_url="http://sb:8080/api/metrics",
                     ml_server_url="http://ml:8000/analyze")
    assert sb.target_url() == "http://sb:8080/api/metrics"
    assert ml.target_url() == "http://ml:8000/analyze"


def test_from_dict_parses_mode_fields():
    cfg = _from_dict({
        "mode": "mlserver",
        "ml_server_url": "http://x:8000/analyze",
        "spring_boot_url": "http://y:8080/api/metrics",
        "api_key": "K1",
    })
    assert cfg.mode == "mlserver"
    assert cfg.ml_server_url == "http://x:8000/analyze"
    assert cfg.spring_boot_url == "http://y:8080/api/metrics"
    assert cfg.api_key == "K1"


def test_env_override_mode_and_urls(monkeypatch):
    monkeypatch.setenv("RADA_MODE", "mlserver")
    monkeypatch.setenv("RADA_ML_SERVER_URL", "http://envml:8000/analyze")
    monkeypatch.setenv("RADA_SPRING_BOOT_URL", "http://envsb:8080/api/metrics")
    monkeypatch.setenv("RADA_API_KEY", "ENVKEY")
    cfg = load_config()
    assert cfg.mode == "mlserver"
    assert cfg.ml_server_url == "http://envml:8000/analyze"
    assert cfg.spring_boot_url == "http://envsb:8080/api/metrics"
    assert cfg.api_key == "ENVKEY"
    assert cfg.target_url() == "http://envml:8000/analyze"


def test_env_invalid_mode_raises(monkeypatch):
    monkeypatch.setenv("RADA_MODE", "garbage")
    with pytest.raises(ValueError):
        load_config()
