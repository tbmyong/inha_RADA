# Retrieval Quality Report (R2)

RADA R2: per-feature 정규화 + cosine distance 도입 효과를 합성 데이터로 측정.

## Setup
- 합성 segment: 90 개 (30 × normal, mining, training)
- window_size: 12 snapshots/segment
- seed: 42 (deterministic)
- 각 segment 를 쿼리로 사용하여 self-exclude self-search, top-K=5

## Results

| Mode | Normalize | Recall@5 | Precision@5 | avg dist (same) | avg dist (other) | Separability |
|---|---|---|---|---|---|---|
| euclidean | False | 1.000 | 1.000 | 1931.8135 | 14687.9971 | 7.60x |
| cosine | True | 1.000 | 0.989 | 0.0044 | 0.0388 | 8.78x |

Separability = avg distance(other scenario) / avg distance(same scenario). 클수록 분리도 우수.

## Confusion (top-5 verdict counts per query scenario)

### Euclidean (raw)

| query \ retrieved | normal | mining | training |
|---|---|---|---|
| **normal** | 150 | 0 | 0 |
| **mining** | 0 | 150 | 0 |
| **training** | 0 | 0 | 150 |

### Cosine (normalized)

| query \ retrieved | normal | mining | training |
|---|---|---|---|
| **normal** | 149 | 0 | 1 |
| **mining** | 0 | 150 | 0 |
| **training** | 4 | 0 | 146 |

## Conclusion

- Recall@5: euclidean 1.000 → cosine 1.000 (시나리오 회수 성능 유지)
- Precision@5: 1.000 → 0.989
- Separability: **7.60x → 8.78x (1.15배 향상)** — same-scenario 와 other-scenario 의 평균 거리 비율이 더 벌어졌다.

큰 스케일 feature (vram_mb, packet_count) 의 raw Euclidean 거리 dominance 가 log1p + min-max 정규화로 사라지고, cosine 이 방향(패턴) 중심 검색을 한 결과. 또한 cosine 의 거리 범위가 [0, 2] 로 고정되어 score breakdown 의 임계값 (_NEAR_DISTANCE_COSINE=0.35) 을 도메인 무관하게 안정적으로 적용할 수 있다. 운영 기본값으로 cosine + normalize 채택. 회귀 안전을 위해 `RETRIEVAL_DISTANCE_MODE=euclidean`, `RETRIEVAL_NORMALIZE=0` 으로 기존 동작 복원 가능.

## How to reproduce

```bash
python tools/retrieval_quality_eval.py
```
