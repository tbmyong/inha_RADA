"""Statistical embedding for time-series segment.

deep encoder 가 아닌 통계 기반 vector 로 segment 를 표현한다.
feature 10개 × stat 8개 = 80차원 고정.
"""
from __future__ import annotations
import math
from typing import List

FEATURES = (
    "cpu_percent",
    "memory_percent",
    "gpu_percent",
    "gpu_vram_mb",
    "gpu_power_w",
    "disk_read_mb",
    "disk_write_mb",
    "inbound_mb",
    "outbound_mb",
    "external_packet_count",
)

STAT_DIM = 8  # mean, std, min, max, last, slope, p95, range
EMBED_DIM = len(FEATURES) * STAT_DIM


def _finite(v: float) -> float:
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return f


def _stats(values: List[float]) -> List[float]:
    n = len(values)
    if n == 0:
        return [0.0] * STAT_DIM
    vals = [_finite(v) for v in values]
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / n
    std = math.sqrt(var)
    vmin = min(vals)
    vmax = max(vals)
    last = vals[-1]
    if n >= 2:
        slope = (vals[-1] - vals[0]) / (n - 1)
    else:
        slope = 0.0
    sorted_vals = sorted(vals)
    # p95
    idx = max(0, min(n - 1, int(math.ceil(0.95 * n)) - 1))
    p95 = sorted_vals[idx]
    rng = vmax - vmin
    return [
        _finite(mean), _finite(std), _finite(vmin), _finite(vmax),
        _finite(last), _finite(slope), _finite(p95), _finite(rng),
    ]


def build_embedding(segment: dict) -> List[float]:
    """segment dict → fixed-length statistical vector."""
    snaps = (segment or {}).get("snapshots") or []
    out: List[float] = []
    for feat in FEATURES:
        series = [s.get(feat) if isinstance(s, dict) else None for s in snaps]
        out.extend(_stats(series))
    # 길이 보장
    if len(out) != EMBED_DIM:
        # 방어적: 부족하면 패딩
        out = (out + [0.0] * EMBED_DIM)[:EMBED_DIM]
    return out
