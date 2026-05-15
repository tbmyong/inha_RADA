"""client_core.sender.local_queue 테스트."""
import json
import threading

import pytest

from client_core.sender import LocalQueue


# ---------------------------------------------------------- in-memory (회귀)
def test_put_and_pop_fifo():
    q = LocalQueue(max_size=10)
    q.put({"id": 1})
    q.put({"id": 2})
    assert len(q) == 2
    assert q.pop() == {"id": 1}
    assert q.pop() == {"id": 2}
    assert q.pop() is None


def test_overflow_drops_oldest():
    q = LocalQueue(max_size=3)
    for i in range(5):
        q.put({"i": i})
    assert len(q) == 3
    assert q.dropped_count == 2
    items = q.drain()
    assert [it["i"] for it in items] == [2, 3, 4]
    assert len(q) == 0


def test_drain_returns_all_and_clears():
    q = LocalQueue(max_size=5)
    q.put("a")
    q.put("b")
    drained = q.drain()
    assert drained == ["a", "b"]
    assert len(q) == 0


def test_invalid_max_size():
    with pytest.raises(ValueError):
        LocalQueue(max_size=0)


def test_iter_preserves_order():
    q = LocalQueue(max_size=10)
    for v in [1, 2, 3]:
        q.put(v)
    assert list(q) == [1, 2, 3]


# ------------------------------------------------------------ persistence
def test_disk_put_appends_jsonl_line(tmp_path):
    p = tmp_path / "queue.jsonl"
    q = LocalQueue(max_size=10, queue_path=p)
    q.put({"id": 1})
    q.put({"id": 2})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l) for l in lines] == [{"id": 1}, {"id": 2}]


def test_disk_pop_compacts_file(tmp_path):
    p = tmp_path / "queue.jsonl"
    q = LocalQueue(max_size=10, queue_path=p)
    q.put({"id": 1})
    q.put({"id": 2})
    q.put({"id": 3})
    assert q.pop() == {"id": 1}
    lines = p.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l) for l in lines] == [{"id": 2}, {"id": 3}]


def test_disk_drain_compacts_file(tmp_path):
    p = tmp_path / "queue.jsonl"
    q = LocalQueue(max_size=10, queue_path=p)
    for i in range(3):
        q.put({"i": i})
    q.drain()
    assert p.read_text(encoding="utf-8") == ""


def test_disk_overflow_drops_oldest_and_increments_counter(tmp_path):
    p = tmp_path / "queue.jsonl"
    q = LocalQueue(max_size=2, queue_path=p)
    for i in range(5):
        q.put({"i": i})
    assert q.dropped_count == 3
    lines = p.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l) for l in lines] == [{"i": 3}, {"i": 4}]


def test_load_skips_corrupt_lines(tmp_path):
    p = tmp_path / "queue.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"ok": 1}),
                "{not valid json",
                "",
                json.dumps({"ok": 2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    q = LocalQueue(max_size=10, queue_path=p)
    assert len(q) == 2
    assert q.corrupt_skipped_count == 1
    assert q.drain() == [{"ok": 1}, {"ok": 2}]


def test_concurrent_puts(tmp_path):
    p = tmp_path / "queue.jsonl"
    q = LocalQueue(max_size=200, queue_path=p)

    N = 100
    threads = []

    def worker(start):
        for i in range(start, start + 10):
            q.put({"i": i})

    for s in range(0, N, 10):
        t = threading.Thread(target=worker, args=(s,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    assert len(q) == N
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == N
    ids = sorted(json.loads(l)["i"] for l in lines)
    assert ids == list(range(N))


def test_max_bytes_drops_oldest(tmp_path):
    p = tmp_path / "queue.jsonl"
    # 각 라인은 대략 ~30바이트 이상
    q = LocalQueue(max_size=1000, queue_path=p, max_bytes=120)
    for i in range(50):
        q.put({"payload": "x" * 20, "i": i})
    assert p.stat().st_size <= 120
    assert q.dropped_count > 0


def test_queue_path_none_no_disk_io(tmp_path):
    # 회귀: queue_path=None 인 경우 디스크 파일은 생성되지 않음
    q = LocalQueue(max_size=10)
    q.put({"x": 1})
    q.pop()
    # tmp_path 안에 어떤 파일도 만들지 않음
    assert list(tmp_path.iterdir()) == []
