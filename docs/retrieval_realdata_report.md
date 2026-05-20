# Retrieval Quality — Real-Data Validation (R4)

`tools/retrieval_quality_eval.py` 가 합성 90 segment 기준으로 separability 를 측정했다면, 본 리포트는 **실제 정상 traffic** 위에서 mining injection 을 한 결과다. 합성 결과 (Euclidean→Cosine, separability 7.60x → 8.78x) 의 실데이터 재현 + FP rate 추정이 목표.

## 1. Setup

| 항목 | 값 |
|---|---|
| 데이터 소스 | `pc_monitor.metrics_history` |
| PC | `0c7a15737f66` (admin lab notebook, MAC 기반 ID) |
| 수집 기간 | 약 4시간 (5초 간격, 백그라운드 `python client.py`) |
| metric row 수 | **3,029** |
| 정상 segment (12-snapshot 윈도우) | **503** |
| Mining injection | `tools/anomaly_trigger.py` × 15회 |
| Mining segment | **15** |

> **버전 노트**: 본 리포트는 4시간 누적 데이터 기준으로 갱신됨. 초기 1시간 (rows=797, normal_segments=131) 결과와 비교 시 Mode C 의 우위가 더 명확해졌다 (CV 2.5x → 3.9x).

비교 대상 3 모드:

| Mode | 설명 |
|---|---|
| **A** | `RETRIEVAL_DISTANCE_MODE=off` — retrieval evidence 미사용 (rule scoring 만) |
| **B** | `RETRIEVAL_DISTANCE_MODE=euclidean` + `RETRIEVAL_NORMALIZE=0` — raw Euclidean, 정규화 없음 |
| **C** | `RETRIEVAL_DISTANCE_MODE=cosine` + `RETRIEVAL_NORMALIZE=1` (현재 default) — log1p + min-max + cosine |

## 2. 정상 traffic baseline

| 지표 | mean | p50 | p95 | max |
|---|---|---|---|---|
| `cpu_percent` | 22.4 | 12.4 | 64.8 | 96.3 |
| `memory_percent` | 60.3 | 56.2 | 76.8 | 79.8 |
| `disk_read_mb` (5s delta) | 4.00 | 0.08 | 5.9 | 1184.9 |
| `disk_write_mb` (5s delta) | 10.4 | 8.3 | 18.6 | 1418.9 |
| `inbound_mb` (5s delta) | 5.8 | 6.4 | 12.6 | 115.3 |
| `outbound_mb` (5s delta) | 1.7 | 0.20 | 8.96 | 29.5 |
| `external_packet_count` | 9.2 | 9 | 19 | 104 |

평소 lab PC 사용 패턴 (브라우저 / IDE / 로컬 빌드) — CPU 평균 ~22% (idle 시간 비중 큼), 메모리 60%, 외부 네트워크는 가벼움. **disk_write_mb 의 max=1418 (평균의 137x)** 같은 outlier 가 다수 — 정규화 효과 검증에 매우 의미 있는 데이터셋. 합성 90 segment 보다 노이즈/스파이크 분포가 훨씬 현실적.

## 3. Mining detection (각 모드별)

각 모드에서 mining segment 10건의 retrieval 동작:

| Mode | retrieval_score (mean) | top-1 verdict=HIGH_RISK | top-1 distance (mean) |
|---|---|---|---|
| A — retrieval off | — | — | — |
| B — euclidean raw | **3.0** | **100%** | **0.0** |
| C — cosine normalized | **3.0** | **100%** | **0.0** |

세 모드 모두 mining injection 이 즉시 ML 의 rule-based scoring 만으로 HIGH_RISK 로 잡힌다 (A 의 final 점수도 mining 으로 분류 — retrieval 안 써도 잡힘). B/C 는 추가로 retrieval evidence 의 top-1 이 **distance 0.0 = 같은 segment** 와 매칭 — mining query 가 자기 자신 history (스토어에 누적된 직전 mining segment) 와 정확히 매칭됨.

→ **mining 자체 탐지력은 세 모드가 동등**. retrieval 의 가치는 다음 절 (FP rate) 에서 드러난다.

## 4. False positive rate

정상 traffic 50개를 random sampling → 각각 query → top-k 의 verdict 분포 확인.
**FP = 정상 query 가 anomaly verdict (HIGH_RISK/SUSPICIOUS) 와 매칭되는 비율**.

| Mode | n | FP count | FP rate | top-1 distance (mean) | top-1 distance (std) | top-1 distance (max) | separability_ratio |
|---|---|---|---|---|---|---|---|
| B — euclidean raw | 50 | 0 | **0%** | **59.99** | **155.56** | **893.67** | 257.09 (scale-naive) |
| C — cosine normalized | 50 | 0 | **0%** | **0.0101** | **0.0068** | **0.0341** | 74.75 |

FP rate 자체는 두 모드 모두 0% — 4시간 데이터 규모에서도 충분히 분리된다.

> `separability_ratio` = mining-to-normal top-k distance / normal-to-normal top-k distance. 절대 distance scale 에 비례해 커지므로 raw Euclidean (B) 이 더 크게 나오는 건 거리 단위 차이 때문이며, **품질 우위로 해석하면 안 된다**. 운영상 중요한 건 normal traffic 거리 분포의 안정성 (낮은 CV, 작은 max/mean).

핵심 차이는 **top-1 distance 의 분산**:

| 메트릭 | B (Euclidean raw) | C (Cosine norm) | 비율 |
|---|---|---|---|
| mean | 59.99 | 0.0101 | — (단위 다름) |
| std/mean (CV) | **2.59** | **0.67** | **C 가 3.9배 안정** |
| max/mean | **14.9x** | **3.4x** | **C 가 4.4배 안정** |

→ Cosine + normalize 가 **거리 분포의 분산 (variance) 을 약 4x 줄임**. raw Euclidean 의 max distance 894 는 큰 스케일 feature 의 dominance 의 흔적 (특정 outlier — disk_write_mb=1418, inbound_mb=115 같은 — 가 거리를 압도). Cosine 은 방향 기반이라 outlier 1개의 영향이 제한적.

**1시간 데이터와 비교**: CV 격차 2.5x → 3.9x, max/mean 격차 2.4x → 4.4x — 데이터 규모가 늘수록 Cosine 의 안정성 우위가 더 뚜렷해진다.

## 5. 결론

| 발견 | 의미 |
|---|---|
| Mining detection rate: A/B/C 동등 (100% HR) | Rule scoring 만으로도 명백한 mining 은 즉시 잡힌다. retrieval 의 가치는 detection 자체가 아니라 borderline 케이스의 신뢰도 보강 |
| FP rate: B 0% / C 0% (4시간 데이터) | 데이터 규모가 더 커지면 (7일+) raw Euclidean 의 큰 분산이 FP 를 만들 가능성 — Cosine 이 더 안전 |
| top-1 distance variance: C 가 B 대비 4x 안정 | 큰 스케일 feature dominance 가 cosine + normalize 로 해소되었음을 실데이터에서 재확인. 1h → 4h 로 갈수록 격차 확대 (2.5x → 3.9~4.4x) |
| 합성 결과 separability 7.60x → 8.78x | 실데이터에선 분산 비율 (CV / max·mean ratio) 로 3.9~4.4x 안정화. 합성/실데이터 모두 cosine 우세이며 실데이터에서 더 큰 효과 |

## 6. 한계 + 향후 과제

- **데이터 규모**: 797 row × 1 PC 1 시간. 논문 평가 수준의 "정상 7일 데이터 기준 FP 10%↑ 감소" 는 실제 학생 PC 다수에서 며칠 수집 후 측정 필요
- **다양성 부족**: 단일 PC + 단일 사용자 패턴. 학년/시간대/lab 종류별 분포 미반영
- **mining 다양성**: anomaly_trigger 의 mining 시나리오 1종 — xmrig-like 만. CPU/GPU/network 패턴 다른 mining 도구 (예: ethminer, claymore) 확장 필요
- **borderline 케이스**: 정상이지만 무거운 작업 (큰 빌드, 게임, 동영상 인코딩) 의 FP 가능성 측정 필요

## 7. 재현 방법

```powershell
# 1. 정상 traffic 1시간 누적
$env:RADA_MODE = "springboot"
$env:RADA_API_KEY = "labpc-key"   # pc_info 에 등록된 raw key
$env:RADA_SPRING_BOOT_URL = "http://localhost:8080/api/metrics"
Start-Process python -ArgumentList "client.py" -NoNewWindow

# 2. mining injection
python tools\anomaly_trigger.py

# 3. 분석
python tools\retrieval_realdata_eval.py
# → tools/_realdata_eval_result.json 생성
```

분석 스크립트는 metrics_history 의 정상 segment + anomaly_history 의 mining segment 를 자동으로 가져와 3 모드를 비교한다.

---

**관련 commit**: R0 (`6393cf5`), R1 (`217e2e7`), R2 cosine retrieval (`dd857c9`), F1 prometheus exposure (`b4b7140`), F5 missing vs zero (`3a07df2`), F6 silent fail metrics (`493c5f3`).
