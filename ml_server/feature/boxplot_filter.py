"""BS-iForest 박스플롯 필터 (Chen et al. 2023 Algorithm 1)."""
import numpy as np


def boxplot_has_outlier(arr: np.ndarray) -> bool:
    """1D 배열에 IQR 기준 이상치가 존재하는지 확인."""
    if len(arr) < 4:
        return True
    q1, q3  = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr     = q3 - q1
    lower   = q1 - 1.5 * iqr
    upper   = q3 + 1.5 * iqr
    return bool(np.any((arr < lower) | (arr > upper)))


def filter_training_data_by_boxplot(X_raw: np.ndarray) -> np.ndarray:
    """학습 데이터에서 박스플롯 기준 이상치를 포함하는 서브셋만 선별."""
    n_features  = X_raw.shape[1]
    outlier_mask = np.zeros(len(X_raw), dtype=bool)

    for feature_idx in range(n_features):
        col  = X_raw[:, feature_idx]
        q1   = np.percentile(col, 25)
        q3   = np.percentile(col, 75)
        iqr  = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_mask |= (col < lower) | (col > upper)

    outlier_idx = np.where(outlier_mask)[0]
    normal_idx  = np.where(~outlier_mask)[0]

    if len(outlier_idx) == 0:
        return X_raw

    max_normal = min(len(normal_idx), len(outlier_idx) * 3)
    rng = np.random.RandomState(42)
    if max_normal > 0:
        selected_normal = rng.choice(normal_idx, max_normal, replace=False)
        selected_idx    = np.concatenate([outlier_idx, selected_normal])
    else:
        selected_idx = outlier_idx

    return X_raw[np.sort(selected_idx)]
