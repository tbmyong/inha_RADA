"""sklearn IsolationForest 인터페이스 검증 (RIF에서 표준 IF로 교체됨)."""
import numpy as np
import pytest

from sklearn.ensemble import IsolationForest


@pytest.fixture
def sample_data():
    rng = np.random.RandomState(0)
    X = rng.randn(120, 10)
    # 명백한 이상치 추가
    X[-3:] += 50.0
    return X


def test_predict_shape_and_values(sample_data):
    model = IsolationForest(
        n_estimators=10, contamination=0.05, random_state=42, n_jobs=-1,
    )
    model.fit(sample_data)
    preds = model.predict(sample_data)
    assert preds.shape == (len(sample_data),)
    assert set(np.unique(preds)).issubset({-1, 1})

    scores = model.decision_function(sample_data)
    assert scores.shape == (len(sample_data),)
    assert np.isfinite(scores).all()


def test_outliers_flagged(sample_data):
    """주입된 이상치(마지막 3건)는 -1로 분류되어야 한다."""
    model = IsolationForest(
        n_estimators=50, contamination=0.05, random_state=42, n_jobs=-1,
    )
    model.fit(sample_data)
    preds = model.predict(sample_data)
    assert (preds[-3:] == -1).all()
