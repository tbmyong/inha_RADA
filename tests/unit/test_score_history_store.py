"""가중 평균 (최근일수록 1.0, 오래될수록 0.2)."""
from ml_server.storage import score_history_store


def test_weighted_average_single_value():
    assert score_history_store.weighted_average([5.0]) == 5.0


def test_weighted_average_uniform_values_returns_same():
    assert abs(score_history_store.weighted_average([3.0]*5) - 3.0) < 1e-9


def test_weighted_average_recent_value_dominates():
    """[1, 1, 1, 1, 10] → 가중치 [0.2, 0.4, 0.6, 0.8, 1.0]
       값 = (0.2+0.4+0.6+0.8 + 10) / 3.0 = 12.0/3.0 = 4.0
    """
    out = score_history_store.weighted_average([1, 1, 1, 1, 10])
    assert abs(out - 4.0) < 1e-9


def test_append_rule_score_returns_weighted_avg():
    # 깨끗한 키 사용
    pc, slot = "test-pc-rule", "free"
    score_history_store.rule_score_history.pop((pc, slot), None)

    a = score_history_store.append_rule_score(pc, slot, 4.0)
    assert abs(a - 4.0) < 1e-9
    b = score_history_store.append_rule_score(pc, slot, 8.0)
    # [4, 8] 가중치 [0.8, 1.0] → (3.2 + 8.0)/1.8 = 6.222...
    assert abs(b - (3.2 + 8.0) / 1.8) < 1e-9


def test_append_ml_score_appends_to_pc_score_history():
    pc, slot = "test-pc-ml", "class"
    score_history_store.pc_score_history.pop((pc, slot), None)
    score_history_store.append_ml_score(pc, slot, -0.3)
    assert (pc, slot) in score_history_store.pc_score_history
    assert list(score_history_store.pc_score_history[(pc, slot)]) == [-0.3]
