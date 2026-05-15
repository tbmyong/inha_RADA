"""USE_REAL_CLAUDE / ANTHROPIC_API_KEY 환경변수화 단위 테스트."""
from __future__ import annotations

from ml_server import config


def test_use_real_claude_default_false(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("USE_REAL_CLAUDE", raising=False)
    assert config.use_real_claude() is False


def test_use_real_claude_true_when_key_set(monkeypatch):
    monkeypatch.delenv("USE_REAL_CLAUDE", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-xxx")
    assert config.use_real_claude() is True


def test_use_real_claude_explicit_override(monkeypatch):
    """USE_REAL_CLAUDE=false + 키 설정 → 명시적 override가 우선해 False."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-xxx")
    monkeypatch.setenv("USE_REAL_CLAUDE", "false")
    assert config.use_real_claude() is False


def test_get_anthropic_api_key_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert config.get_anthropic_api_key() is None
