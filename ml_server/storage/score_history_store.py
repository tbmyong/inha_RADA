"""ML 점수 / 룰 점수 누적 히스토리 — 가중 평균.

키는 (pc_id, slot) 튜플 — 슬롯 혼용 방지.
"""
from collections import deque
from typing import Dict, Tuple

from ..config import SCORE_WINDOW

# (pc_id, slot) → deque[float]
pc_score_history:   Dict[Tuple[str, str], deque] = {}
rule_score_history: Dict[Tuple[str, str], deque] = {}

# P1-3 (docs/fp_field_analysis_v0.6.md §7-P1-3): rule_score_history 에
# 0 점이 연속 N회 누적되면 deque 를 즉시 비워 가중 평균이 0 으로 빨리
# 수렴하도록 한다 (=episode score 빠른 decay). N 은 scoring_policy.yaml
# 의 episode_dedupe.episode_decay_after_normal_count.
_rule_zero_streak: Dict[Tuple[str, str], int] = {}


def weighted_average(scores: list) -> float:
    """가중 평균: 최근일수록 가중치 1.0, 오래될수록 0.2까지 선형 감소."""
    n = len(scores)
    if n == 0:
        return 0.0
    weights = [max(0.2, 1.0 - 0.2 * (n - 1 - i)) for i in range(n)]
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


def append_ml_score(pc_id: str, slot: str, score: float) -> float:
    key = (pc_id, slot)
    if key not in pc_score_history:
        pc_score_history[key] = deque(maxlen=SCORE_WINDOW)
    pc_score_history[key].append(score)
    return weighted_average(list(pc_score_history[key]))


def append_rule_score(pc_id: str, slot: str, score: float, maxlen: int = 5) -> float:
    key = (pc_id, slot)
    if key not in rule_score_history:
        rule_score_history[key] = deque(maxlen=maxlen)
    rule_score_history[key].append(score)

    # P1-3 fast decay: 연속 0 점이 임계 N 회 도달 시 deque 즉시 clear.
    # 한 번 튄 episode 점수가 정상 window 가 이어진 뒤에도 가중 평균에
    # 남아 anomaly 가 5초마다 누적 저장되는 문제를 차단.
    try:
        from ..policy import get_scoring_policy
        decay_n = int(get_scoring_policy().episode_dedupe.episode_decay_after_normal_count)
    except Exception:
        decay_n = 0
    if decay_n > 0:
        if score <= 0:
            streak = _rule_zero_streak.get(key, 0) + 1
            _rule_zero_streak[key] = streak
            if streak >= decay_n:
                rule_score_history[key].clear()
                _rule_zero_streak[key] = 0
        else:
            _rule_zero_streak[key] = 0

    return weighted_average(list(rule_score_history[key]))


def reset_rule_score_history() -> None:
    """테스트용: rule_score_history + zero-streak 초기화."""
    rule_score_history.clear()
    _rule_zero_streak.clear()
