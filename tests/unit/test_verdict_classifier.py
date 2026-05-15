"""verdict 4단계 경계값 (CONFIRMED_MINING은 HIGH_RISK로 통합)."""
from ml_server.scorer.verdict_classifier import classify_verdict


def test_normal_just_below_5():
    v, s = classify_verdict(final_score=4.99, process_score=0)
    assert v == "NORMAL" and s == "NORMAL"


def test_observe_at_5():
    v, s = classify_verdict(final_score=5.0, process_score=0)
    assert v == "OBSERVE" and s == "LOW"


def test_observe_just_below_9():
    v, s = classify_verdict(final_score=8.99, process_score=0)
    assert v == "OBSERVE" and s == "LOW"


def test_suspicious_at_9():
    v, s = classify_verdict(final_score=9.0, process_score=0)
    assert v == "SUSPICIOUS" and s == "MEDIUM"


def test_suspicious_just_below_14():
    v, s = classify_verdict(final_score=13.99, process_score=0)
    assert v == "SUSPICIOUS" and s == "MEDIUM"


def test_high_risk_at_14():
    v, s = classify_verdict(final_score=14.0, process_score=0)
    assert v == "HIGH_RISK" and s == "HIGH"


def test_process_score_does_not_override_low_final():
    """CONFIRMED_MINING은 verdict가 아닌 alerts[0].type으로 표현되므로,
    process_score가 높아도 verdict는 final_score만으로 결정된다."""
    v, _ = classify_verdict(final_score=0.5, process_score=13)
    assert v == "NORMAL"
