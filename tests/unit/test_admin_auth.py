"""Admin token auth — /admin/reload-policy 와 DELETE /history/{pc_id} 검증."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from ml_server.main import app


@pytest.fixture
def _unset_token(monkeypatch):
    monkeypatch.delenv("RADA_ADMIN_TOKEN", raising=False)
    yield


@pytest.fixture
def _set_token(monkeypatch):
    monkeypatch.setenv("RADA_ADMIN_TOKEN", "secret-T")
    yield "secret-T"


def test_reload_policy_no_token_required_when_env_unset(_unset_token):
    with TestClient(app) as client:
        resp = client.post("/admin/reload-policy")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "scoring_policy_version" in body
        assert "allowlist_version" in body


def test_reload_policy_rejects_missing_token(_set_token):
    with TestClient(app) as client:
        resp = client.post("/admin/reload-policy")
        assert resp.status_code == 401


def test_reload_policy_rejects_wrong_token(_set_token):
    with TestClient(app) as client:
        resp = client.post("/admin/reload-policy", headers={"X-Admin-Token": "WRONG"})
        assert resp.status_code == 401


def test_reload_policy_accepts_correct_token(_set_token):
    with TestClient(app) as client:
        resp = client.post(
            "/admin/reload-policy", headers={"X-Admin-Token": _set_token}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_clear_history_rejects_without_token(_set_token):
    with TestClient(app) as client:
        resp = client.delete("/history/pc-no-such")
        assert resp.status_code == 401


def test_clear_history_accepts_with_token(_set_token):
    with TestClient(app) as client:
        resp = client.delete(
            "/history/pc-no-such", headers={"X-Admin-Token": _set_token}
        )
        assert resp.status_code == 200


def test_clear_history_open_when_token_unset(_unset_token):
    """RADA_ADMIN_TOKEN 미설정 → 개발 기본 (bypass)."""
    with TestClient(app) as client:
        resp = client.delete("/history/pc-no-such")
        assert resp.status_code == 200


def test_status_includes_policy_versions(_unset_token):
    with TestClient(app) as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "scoring_policy_version" in body
        assert "allowlist_version" in body
