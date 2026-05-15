"""Rotated Isolation Forest (Monemizadeh & Kiani 2025).

QR 분해로 생성한 직교 회전행렬을 트리마다 적용하여
axis-aligned ghost cluster + inter-cluster ghost cluster 동시 제거.
"""
import numpy as np
from sklearn.ensemble import IsolationForest


class RotatedIsolationForest:
    """sklearn IsolationForest 호환 인터페이스.

    fit(X) / decision_function(X) / predict(X)
    decision_function: 낮을수록 이상 (sklearn IF 동일 방향)
    predict: -1=이상, 1=정상
    """

    def __init__(
        self,
        n_estimators:  int   = 100,
        contamination: float = 0.05,
        random_state:  int   = 42,
    ):
        self.n_estimators  = n_estimators
        self.contamination = contamination
        self.random_state  = random_state
        self.trees:             list = []
        self.rotation_matrices: list = []
        self._threshold:        float = 0.0

    def fit(self, X: np.ndarray) -> "RotatedIsolationForest":
        d   = X.shape[1]
        rng = np.random.RandomState(self.random_state)

        self.trees             = []
        self.rotation_matrices = []

        for _ in range(self.n_estimators):
            # 랜덤 정규분포 행렬 → QR 분해 → 직교행렬 Q (거리·각도 보존)
            A = rng.randn(d, d)
            Q, _ = np.linalg.qr(A)

            X_rot = X @ Q

            tree = IsolationForest(
                n_estimators=1,
                contamination=self.contamination,
                random_state=int(rng.randint(0, 100000)),
                max_samples=min(256, len(X)),
            )
            tree.fit(X_rot)
            self.trees.append(tree)
            self.rotation_matrices.append(Q)

        train_scores = self.decision_function(X)
        self._threshold = float(
            np.percentile(train_scores, self.contamination * 100)
        )
        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        scores = np.zeros(len(X))
        for tree, Q in zip(self.trees, self.rotation_matrices):
            X_rot   = X @ Q
            scores += tree.decision_function(X_rot)
        return scores / len(self.trees)

    def predict(self, X: np.ndarray) -> np.ndarray:
        scores = self.decision_function(X)
        return np.where(scores < self._threshold, -1, 1)
