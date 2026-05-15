"""Retrieval store add + search + clear_pc 단위 테스트."""
from ml_server.retrieval import retrieval_store as RS


def _seg(pc_id, slot, ts):
    return {
        "segment_id": f"{pc_id}:{slot}:{ts}",
        "pc_id": pc_id,
        "slot": slot,
        "start_ts": ts,
        "end_ts": ts,
        "window_size": 12,
        "snapshots": [],
    }


def setup_function(_):
    RS.reset_store()


def test_search_empty_returns_empty():
    seg = _seg("pc-1", "class", "T0")
    out = RS.search_similar(seg, [0.0] * 80, top_k=3)
    assert out == []


def test_topk_sorted_ascending_by_distance():
    RS.add_segment(_seg("p-near", "class", "T1"), [1.0] * 80, "NORMAL", 0.0)
    RS.add_segment(_seg("p-far",  "class", "T2"), [9.0] * 80, "NORMAL", 0.0)
    RS.add_segment(_seg("p-mid",  "class", "T3"), [3.0] * 80, "NORMAL", 0.0)

    q = _seg("pc-q", "class", "TQ")
    res = RS.search_similar(q, [1.0] * 80, top_k=3)
    assert [r["pc_id"] for r in res] == ["p-near", "p-mid", "p-far"]
    dists = [r["distance"] for r in res]
    assert dists == sorted(dists)


def test_clear_pc_removes_only_that_pc():
    RS.add_segment(_seg("pc-a", "class", "T1"), [0.0] * 80, "NORMAL", 0.0)
    RS.add_segment(_seg("pc-b", "class", "T2"), [0.0] * 80, "NORMAL", 0.0)
    assert RS.clear_pc("pc-a") is True
    remaining_pcs = [s["pc_id"] for s in RS.segment_history_by_slot["class"]]
    assert remaining_pcs == ["pc-b"]
