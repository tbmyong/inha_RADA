"""numpy 타입 → Python 기본 타입 변환.

requests.post(json=...)는 numpy.bool_, numpy.integer 등을 처리 못함.
"""
from __future__ import annotations

import numpy as np


def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(i) for i in obj]
    if isinstance(obj, tuple):
        return [sanitize_for_json(i) for i in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj
