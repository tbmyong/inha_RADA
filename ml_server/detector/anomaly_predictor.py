"""앙상블 모델 학습 + 예측 (IsolationForest + LOF + RobustScaler).

기존 ml_server.py train_model / predict_anomaly 그대로 이전.
"""
# TODO(future): LOF sigmoid → percentile 보정 검토
# TODO(future): soft voting + persistence 검토
from collections import deque
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

from ..config import (
    CONTAMINATION, MIN_TRAIN_SIZE, LOF_WINDOW_SIZE, SCORE_WINDOW,
)
from ..feature.feature_builder import (
    extract_features_from_snapshot, extract_features_from_metrics,
)
from ..feature.boxplot_filter import filter_training_data_by_boxplot
from ..model.requests import MetricsRequest
from ..silent_fail_counters import increment as _bump_silent_fail
from ..storage import pc_history_store, model_store, score_history_store


def train_model(pc_id: str, slot: str) -> bool:
    try:
        history = pc_history_store.pc_train_history.get(pc_id, {}).get(slot, [])
        if len(history) < MIN_TRAIN_SIZE:
            return False

        X_raw = []
        for snap in history:
            feat = extract_features_from_snapshot(snap)
            if feat:
                X_raw.append(feat)

        if len(X_raw) < MIN_TRAIN_SIZE:
            return False

        X_raw = np.array(X_raw)

        scaler   = RobustScaler()
        X_scaled = scaler.fit_transform(X_raw)

        contamination = CONTAMINATION.get(slot, 0.05)

        # ── Isolation Forest ──
        X_filtered   = filter_training_data_by_boxplot(X_scaled)
        has_filtered = len(X_filtered) >= MIN_TRAIN_SIZE

        if_model = IsolationForest(
            contamination=contamination,
            n_estimators=100,
            random_state=42,
            n_jobs=-1,
        )
        if_model.fit(X_filtered if has_filtered else X_scaled)

        # ── Local Outlier Factor (kd_tree, n_jobs=-1, novelty=True) ──
        lof_train = X_scaled[-LOF_WINDOW_SIZE:] if len(X_scaled) > LOF_WINDOW_SIZE else X_scaled

        lof_model = LocalOutlierFactor(
            contamination=contamination,
            novelty=True,
            n_neighbors=min(20, len(lof_train) - 1),
            algorithm='kd_tree',
            n_jobs=-1,
        )
        lof_model.fit(lof_train)

        new_model = {
            "if_model":         if_model,
            "lof_model":        lof_model,
            "scaler":           scaler,
            "sample_count":     len(X_raw),
            "lof_window_size":  len(lof_train),
            "contamination":    contamination,
            "boxplot_filtered": has_filtered,
        }
        # atomic swap (threading.Lock으로 보호)
        model_store.set_model(pc_id, slot, new_model)
        return True

    except Exception as e:
        print(f"[학습 실패] {pc_id}/{slot}: {e}")
        _bump_silent_fail("model_train_failure_count")
        return False


def predict_anomaly(pc_id: str, slot: str, metrics: MetricsRequest) -> dict:
    model_info = model_store.get_model(pc_id, slot)

    if not model_info:
        sample_count = len(pc_history_store.pc_train_history.get(pc_id, {}).get(slot, []))
        return {
            "available":      False,
            "reason":         f"학습 데이터 수집 중 ({sample_count}/{MIN_TRAIN_SIZE}건)",
            "is_anomaly":     None,
            "weighted_score": None,
            "if_score":       None,
            "lof_score":      None,
            "sample_count":   None,
        }

    try:
        features = extract_features_from_metrics(metrics)
        X_raw    = np.array([features])
        X_scaled = model_info["scaler"].transform(X_raw)

        if_score = float(model_info["if_model"].decision_function(X_scaled)[0])

        lof_raw  = float(model_info["lof_model"].decision_function(X_scaled)[0])
        lof_score = float(2 / (1 + np.exp(-np.clip(lof_raw, -500, 500))) - 1)

        ensemble_score = if_score * 0.6 + lof_score * 0.4

        # 누적 가중 점수
        score_key = (pc_id, slot)
        store = score_history_store.pc_score_history
        if score_key not in store:
            store[score_key] = deque(maxlen=SCORE_WINDOW)
        store[score_key].append(ensemble_score)

        scores   = list(store[score_key])
        n        = len(scores)
        weights  = [max(0.2, 1.0 - 0.2 * (n - 1 - i)) for i in range(n)]
        weighted_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)

        if_anomaly  = int(model_info["if_model"].predict(X_scaled)[0]) == -1
        lof_anomaly = int(model_info["lof_model"].predict(X_scaled)[0]) == -1
        is_anomaly  = if_anomaly and lof_anomaly and weighted_score < 0

        bp = metrics.boxplot_signal
        bp_flag = (bp.get("available") and
                   (bp.get("cpu_iqr_outlier") or bp.get("mem_iqr_outlier")))

        return {
            "available":         True,
            "is_anomaly":        bool(is_anomaly),
            "if_score":          round(if_score, 4),
            "lof_score":         round(lof_score, 4),
            "lof_raw":           round(lof_raw, 4),
            "weighted_score":    round(weighted_score, 4),
            "if_anomaly":        bool(if_anomaly),
            "lof_anomaly":       bool(lof_anomaly),
            "boxplot_flag":      bool(bp_flag),
            "sample_count":      int(model_info["sample_count"]),
            "lof_window_size":   int(model_info["lof_window_size"]),
            "contamination":     float(model_info["contamination"]),
            "boxplot_filtered":  bool(model_info.get("boxplot_filtered", False)),
        }

    except Exception as e:
        _bump_silent_fail("model_predict_failure_count")
        return {
            "available":      False,
            "reason":         f"예측 오류: {e}",
            "is_anomaly":     None,
            "weighted_score": None,
            "if_score":       None,
            "lof_score":      None,
            "sample_count":   None,
        }
