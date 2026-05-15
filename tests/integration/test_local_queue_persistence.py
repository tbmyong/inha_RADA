"""LocalQueue 디스크 영속성 통합 테스트.

인스턴스 A에 put 후 폐기 → 동일 path 로 인스턴스 B 생성 시
복구된 항목 수와 drain 결과가 동일해야 한다.
"""
from agent_core.sender import LocalQueue


def test_persistence_across_instances(tmp_path):
    p = tmp_path / "queue.jsonl"

    a = LocalQueue(max_size=100, queue_path=p)
    payloads = [{"i": i, "v": f"item-{i}"} for i in range(20)]
    for payload in payloads:
        a.put(payload)
    assert len(a) == 20
    del a  # 인스턴스 폐기

    b = LocalQueue(max_size=100, queue_path=p)
    assert len(b) == 20
    assert b.drain() == payloads
    assert len(b) == 0


def test_persistence_preserves_after_pop(tmp_path):
    p = tmp_path / "queue.jsonl"
    a = LocalQueue(max_size=100, queue_path=p)
    for i in range(5):
        a.put({"i": i})
    a.pop()  # i=0 제거
    a.pop()  # i=1 제거
    del a

    b = LocalQueue(max_size=100, queue_path=p)
    assert [it["i"] for it in b.drain()] == [2, 3, 4]


def test_persistence_respects_max_size_on_load(tmp_path):
    p = tmp_path / "queue.jsonl"
    a = LocalQueue(max_size=50, queue_path=p)
    for i in range(50):
        a.put({"i": i})
    del a

    # 더 작은 max_size 로 로드 → 가장 오래된 항목들이 drop
    b = LocalQueue(max_size=10, queue_path=p)
    assert len(b) == 10
    assert b.dropped_count == 40
    assert [it["i"] for it in b.drain()] == list(range(40, 50))
