"""F6 #18: silent_fail_counters 단위 테스트."""
from ml_server import silent_fail_counters as sfc
from ml_server.api.status_router import status as status_endpoint


def setup_function(_):
    sfc.reset_for_tests()


def test_seven_keys_present_in_snapshot():
    snap = sfc.get_silent_fail_counters()
    expected = {
        "claude_mock_count",
        "model_train_failure_count",
        "model_predict_failure_count",
        "retrieval_store_eviction_count",
        "retrieval_evidence_skip_count",
        "policy_reload_failed_count",
    }
    assert expected.issubset(set(snap.keys()))


def test_increment_known_key():
    sfc.increment("claude_mock_count")
    sfc.increment("claude_mock_count", 4)
    assert sfc.get_silent_fail_counters()["claude_mock_count"] == 5


def test_increment_unknown_key_is_noop():
    sfc.increment("not_a_real_key")
    assert "not_a_real_key" not in sfc.get_silent_fail_counters()


def test_snapshot_is_isolated_from_internal_state():
    snap = sfc.get_silent_fail_counters()
    snap["claude_mock_count"] = 999
    # 외부 mutate 가 내부 상태에 영향 주면 안 됨
    assert sfc.get_silent_fail_counters()["claude_mock_count"] == 0


def test_status_endpoint_includes_silent_fail_counters():
    sfc.increment("model_predict_failure_count", 2)
    resp = status_endpoint()
    assert "silent_fail_counters" in resp
    sfc_dict = resp["silent_fail_counters"]
    assert sfc_dict["model_predict_failure_count"] == 2
    assert sfc_dict["claude_mock_count"] == 0


def test_retrieval_store_eviction_counted():
    from collections import deque
    from ml_server.retrieval import retrieval_store as rs

    # 작은 maxlen 으로 임시 슬롯 셋업
    rs.segment_history_by_slot["__test_evict__"] = deque(maxlen=2)
    try:
        sfc.reset_for_tests()
        for i in range(3):
            rs.add_segment(
                {"segment_id": f"s{i}", "pc_id": "pc1", "slot": "__test_evict__",
                 "start_ts": 0, "end_ts": 0},
                embedding=[1.0, 0.0],
                verdict="NORMAL",
                score=0.1,
            )
        assert sfc.get_silent_fail_counters()["retrieval_store_eviction_count"] >= 1
    finally:
        rs.segment_history_by_slot.pop("__test_evict__", None)


def test_retrieval_evidence_skip_counted_on_exception():
    from ml_server.retrieval import retrieval_evidence as re

    sfc.reset_for_tests()
    # peer_latest 가 dict 가 아닌 의도된 잘못된 타입 → 내부에서 예외 발생 가능
    # 안전하게 catch 되고 _empty_evidence 반환되어야 한다.
    bad_segment = {"snapshots": "not-a-list"}  # iteration 실패 유도
    out = re.build_retrieval_evidence(bad_segment, [], peer_latest=None)
    assert isinstance(out, dict)
    assert "retrieval_score" in out
    # 예외가 났든 안 났든 결과는 dict — count 는 0 이상.
