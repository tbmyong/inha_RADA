"""F6 #7: RADA_LOCAL_QUEUE_PATH 환경변수가 ClientConfig.local_queue_path 를 override."""
from __future__ import annotations

from client_core.config.loader import load_config


def test_env_override_sets_queue_path(monkeypatch, tmp_path):
    p = tmp_path / "queue.jsonl"
    monkeypatch.setenv("RADA_LOCAL_QUEUE_PATH", str(p))
    cfg = load_config()
    assert cfg.local_queue_path == str(p)


def test_env_override_empty_string_disables(monkeypatch):
    monkeypatch.setenv("RADA_LOCAL_QUEUE_PATH", "")
    cfg = load_config()
    assert cfg.local_queue_path is None


def test_no_env_keeps_default_none(monkeypatch):
    monkeypatch.delenv("RADA_LOCAL_QUEUE_PATH", raising=False)
    cfg = load_config()
    assert cfg.local_queue_path is None


def test_localqueue_instantiates_with_env_path(monkeypatch, tmp_path):
    """env 로 path 주입 + LocalQueue 가 그 path 로 동작하는지 단순 확인."""
    from client_core.sender import LocalQueue

    p = tmp_path / "subdir" / "queue.jsonl"
    monkeypatch.setenv("RADA_LOCAL_QUEUE_PATH", str(p))
    cfg = load_config()
    q = LocalQueue(max_size=10, queue_path=cfg.local_queue_path)
    q.put({"x": 1})
    assert p.exists()
    # 새 인스턴스가 복원하는지
    q2 = LocalQueue(max_size=10, queue_path=cfg.local_queue_path)
    assert len(q2) == 1
