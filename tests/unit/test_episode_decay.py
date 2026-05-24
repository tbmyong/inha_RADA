"""P1-3 — Episode score fast decay after sustained normal windows.

docs/fp_field_analysis_v0.6.md §7-P1-3.

Before P1-3, a single big spike (e.g. dos_spike +5 → adjusted ~7) lived
in the rule_score_history deque (maxlen=5) and the weighted average
took several normal windows to bleed down below the OBSERVE threshold.
Anomaly storms (5-second spikes) accumulated dozens of rows.

P1-3: when ``append_rule_score`` receives 0 for N consecutive samples
(``episode_decay_after_normal_count``, default 12 = 1 minute), the
deque is cleared and the running average drops to 0 immediately.
"""
from __future__ import annotations

import pytest

from ml_server.policy import reload_policies, get_scoring_policy
from ml_server.storage.score_history_store import (
    append_rule_score,
    rule_score_history,
    reset_rule_score_history,
)


@pytest.fixture(autouse=True)
def _reset():
    reload_policies()
    reset_rule_score_history()
    yield
    reset_rule_score_history()


def test_decay_constant_yaml_key_loaded():
    p = get_scoring_policy()
    assert p.episode_dedupe.episode_decay_after_normal_count == 12


def test_streak_below_threshold_keeps_history():
    """N-1 zero samples after a spike still leave the spike in the deque."""
    n = get_scoring_policy().episode_dedupe.episode_decay_after_normal_count
    append_rule_score("pc-d1", "free", 7.0)
    for _ in range(n - 1):
        append_rule_score("pc-d1", "free", 0.0)
    # Deque retains entries (weighted average non-zero)
    assert len(rule_score_history[("pc-d1", "free")]) > 0


def test_streak_reaches_threshold_clears_history():
    """N consecutive zeros clears the deque entirely."""
    n = get_scoring_policy().episode_dedupe.episode_decay_after_normal_count
    append_rule_score("pc-d2", "free", 7.0)
    for _ in range(n):
        append_rule_score("pc-d2", "free", 0.0)
    assert len(rule_score_history[("pc-d2", "free")]) == 0
    # Next non-zero starts fresh from 1 entry.
    avg = append_rule_score("pc-d2", "free", 4.0)
    assert avg == pytest.approx(4.0)


def test_nonzero_score_breaks_streak():
    """A positive score between zeros prevents the clear."""
    n = get_scoring_policy().episode_dedupe.episode_decay_after_normal_count
    append_rule_score("pc-d3", "free", 7.0)
    # n-1 zeros, then a positive blip, then n-1 more zeros → no clear yet
    for _ in range(n - 1):
        append_rule_score("pc-d3", "free", 0.0)
    append_rule_score("pc-d3", "free", 1.0)
    for _ in range(n - 1):
        append_rule_score("pc-d3", "free", 0.0)
    # Streak only reached n-1 after the reset → no clear
    assert len(rule_score_history[("pc-d3", "free")]) > 0


def test_decay_only_clears_target_pc_slot():
    """The clear is per-(pc_id, slot) — other PCs unaffected."""
    n = get_scoring_policy().episode_dedupe.episode_decay_after_normal_count
    append_rule_score("pc-a", "free", 5.0)
    append_rule_score("pc-b", "free", 5.0)
    for _ in range(n):
        append_rule_score("pc-a", "free", 0.0)
    assert len(rule_score_history[("pc-a", "free")]) == 0
    assert len(rule_score_history[("pc-b", "free")]) > 0
