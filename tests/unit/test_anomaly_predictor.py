"""anomaly_predictor: model_info["if_model"]이 sklearn IsolationForest인지 검증."""
import numpy as np
from collections import deque

from sklearn.ensemble import IsolationForest

from ml_server.detector import anomaly_predictor
from ml_server.storage import pc_history_store, model_store
from ml_server.config import TRAIN_WINDOW


def _make_snapshot(rng, mean=20.0):
    return {
        "cpu_percent": float(np.clip(rng.normal(mean, 5), 0, 100)),
        "memory_percent": float(np.clip(rng.normal(40, 5), 0, 100)),
        "gpu_percent": 0.0,
        "gpu_vram_mb": 0.0,
        "gpu_total_mb": 8192,
        "disk_read_mb": 0.0,
        "disk_write_mb": 0.0,
        "gpu_power_w": 0.0,
    }


def test_train_model_uses_sklearn_isolation_forest():
    pc_id, slot = "pc-test-if", "free"
    rng = np.random.RandomState(0)

    # 충분한 학습 샘플 주입
    pc_history_store.pc_train_history[pc_id] = {
        slot: deque([_make_snapshot(rng) for _ in range(120)], maxlen=TRAIN_WINDOW),
    }

    ok = anomaly_predictor.train_model(pc_id, slot)
    assert ok is True

    info = model_store.get_model(pc_id, slot)
    assert info is not None
    assert isinstance(info["if_model"], IsolationForest)
