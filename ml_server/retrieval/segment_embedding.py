"""Statistical embedding for time-series segment.

deep encoder 가 아닌 통계 기반 vector 로 segment 를 표현한다.
feature 10개 × stat 8개 = 80차원 고정.

R2: per-feature 정규화 추가. 큰 스케일 (vram_mb, packet_count, outbound_mb 등)
이 거리 계산을 지배하지 않도록 log1p + min-max 로 [0, ~1] 범위에 맞춘다.

기존 build_embedding(segment) 의 반환 차원/순서는 그대로 유지.
값만 정규화된 형태로 바뀐다. (RETRIEVAL_NORMALIZE=0 으로 끄면 raw 통계 그대로)
"""
from __future__ import annotations
import math
import os
from typing import List, Tuple

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

# 정규화 on/off (env). 기본 on.
_NORMALIZE = os.environ.get("RETRIEVAL_NORMALIZE", "1") not in ("0", "false", "False")

# feature 별 (log1p_apply, divisor) — divisor 는 log1p 적용 후 [0,1] 근처로 맞추기 위함.
# percent 류는 그대로 /100. 큰 스케일 (mb, count) 은 log1p 후 작은 divisor.
# 보수적 상한이며 outlier 가 약간 1.0 을 넘는 것은 허용 (cosine 은 norm 무관).
_FEATURE_SCALE: dict = {
    # percent (0~100): 그대로 /100
    "cpu_percent":           (False, 100.0),
    "memory_percent":        (False, 100.0),
    "gpu_percent":           (False, 100.0),
    # 큰 mb/count: log1p 후 정규화
    "gpu_vram_mb":           (True,  math.log1p(24000.0)),   # ~24GB upper
    "gpu_power_w":           (False, 400.0),                  # ~400W upper
    "disk_read_mb":          (True,  math.log1p(500.0)),
    "disk_write_mb":         (True,  math.log1p(500.0)),
    "inbound_mb":            (True,  math.log1p(500.0)),
    "outbound_mb":           (True,  math.log1p(500.0)),
    "external_packet_count": (True,  math.log1p(50000.0)),
}


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


def _normalize_value(feat: str, v: float) -> float:
    """feature 별 정규화. log1p (필요 시) 후 divisor 로 나눔. 음수 안전."""
    use_log, divisor = _FEATURE_SCALE.get(feat, (False, 1.0))
    if divisor <= 0:
        return 0.0
    x = v
    if use_log:
        # 음수는 절대값에 부호 보존
        sign = -1.0 if x < 0 else 1.0
        x = sign * math.log1p(abs(x))
    return x / divisor


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


def _normalize_stats(feat: str, stats: List[float]) -> List[float]:
    """stats = [mean, std, vmin, vmax, last, slope, p95, rng] 를 정규화."""
    # mean/min/max/last/p95: 값 자체 → feature 정규화
    mean, std, vmin, vmax, last, slope, p95, rng = stats
    nmean = _normalize_value(feat, mean)
    nmin = _normalize_value(feat, vmin)
    nmax = _normalize_value(feat, vmax)
    nlast = _normalize_value(feat, last)
    np95 = _normalize_value(feat, p95)
    # std/range: 같은 단위의 변동 — divisor 만 사용 (log1p 미적용 — 차이값이라 0 근처)
    _, divisor = _FEATURE_SCALE.get(feat, (False, 1.0))
    if divisor <= 0:
        nstd = 0.0
        nrng = 0.0
        nslope = 0.0
    else:
        nstd = std / divisor
        nrng = rng / divisor
        # slope: per-step Δ → 더 작은 값. 같은 divisor 사용.
        nslope = slope / divisor
    return [
        _finite(nmean), _finite(nstd), _finite(nmin), _finite(nmax),
        _finite(nlast), _finite(nslope), _finite(np95), _finite(nrng),
    ]


def build_embedding(segment: dict) -> List[float]:
    """segment dict → fixed-length statistical vector.

    RETRIEVAL_NORMALIZE 가 켜져있으면 (기본) per-feature log1p+min-max 정규화 적용.
    """
    snaps = (segment or {}).get("snapshots") or []
    out: List[float] = []
    for feat in FEATURES:
        series = [s.get(feat) if isinstance(s, dict) else None for s in snaps]
        st = _stats(series)
        if _NORMALIZE:
            st = _normalize_stats(feat, st)
        out.extend(st)
    # 길이 보장
    if len(out) != EMBED_DIM:
        out = (out + [0.0] * EMBED_DIM)[:EMBED_DIM]
    return out
