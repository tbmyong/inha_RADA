# Retrieval-Augmented Time-Series Evidence Layer 적용 매뉴얼

## 1. 목적

이 문서는 RADA 프로젝트에 논문 **Anomaly Detection Using Generative Language Models and Deep Feature-Based Time Series Similarity**의 핵심 구조를 적용하기 위한 개발 매뉴얼이다.

적용 범위는 논문 전체 재현이 아니라, RADA 구조에 맞춘 다음 MVP 구현이다.

```text
sliding window segment
→ statistical embedding
→ similar historical segment retrieval
→ peer comparison
→ retrieval score
→ AI Agent evidence prompt
```

즉, 현재 이상 window와 유사한 과거 window를 실제로 검색하고, 검색 결과가 점수와 AI 설명에 반영되도록 만든다.

## 2. 적용 원칙

### 2.1 구현 범위

- DB 스키마는 변경하지 않는다.
- 기존 IF/LOF, rule scoring, context discount 구조는 유지한다.
- Retrieval layer는 ML 서버 내부 메모리 저장소로 먼저 구현한다.
- Retrieval 결과는 `score_breakdown`, `/analyze` 응답, AI Agent prompt에 모두 반영한다.
- 초기 embedding은 deep encoder가 아니라 통계 기반 embedding으로 구현한다.

### 2.2 용어

| 용어 | 의미 |
|---|---|
| snapshot | 5초 단위 단일 metric |
| segment | 최근 1분 또는 5분 snapshot 묶음 |
| embedding | segment를 검색 가능한 숫자 벡터로 변환한 값 |
| retrieved cases | 현재 segment와 유사한 과거 segment top-k |
| peer comparison | 같은 시간대 다른 PC들과 비교한 결과 |
| retrieval score | retrieved cases와 peer mismatch를 기반으로 추가되는 점수 |

## 3. 현재 코드 기준 삽입 위치

현재 `/analyze` 흐름은 `ml_server/api/analyze_router.py`에 있다.

현재 구조:

```text
make_snapshot(metrics)
→ history.append(snapshot)
→ update_train_history(...)
→ maybe_retrain(...)
→ predict_anomaly(...)
→ analyze_pattern(...)
→ run_ai_agent(...)
```

변경 후 구조:

```text
make_snapshot(metrics)
→ history.append(snapshot)
→ update_train_history(...)
→ maybe_retrain(...)
→ predict_anomaly(...)
→ build_segment(history)
→ build_segment_embedding(segment)
→ search_similar_segments(segment)
→ build_retrieval_evidence(...)
→ analyze_pattern(..., retrieval_evidence=evidence)
→ store_segment(segment, verdict, score)
→ run_ai_agent(...)
```

주의: 현재 segment는 검색 전에 저장하지 않는다. 먼저 과거 segment를 검색하고, 최종 verdict와 score가 나온 뒤 현재 segment를 저장해야 자기 자신이 top-k에 잡히지 않는다.

## 4. 신규 파일 계획

### 4.1 `ml_server/feature/segment_builder.py`

역할:

- 최근 snapshot history에서 segment 생성
- 1분 segment는 최근 12개 snapshot 사용
- 5분 segment는 최근 60개 snapshot 사용
- MVP에서는 1분 segment부터 구현

예상 함수:

```python
def build_segment(pc_id: str, slot: str, history: deque, window_size: int = 12) -> dict | None:
    ...
```

반환 예:

```json
{
  "segment_id": "pc-01:class:2026-05-15T10:00:00",
  "pc_id": "pc-01",
  "slot": "class",
  "start_ts": "2026-05-15T10:00:00",
  "end_ts": "2026-05-15T10:00:55",
  "window_size": 12,
  "snapshots": [...]
}
```

### 4.2 `ml_server/feature/segment_embedding.py`

역할:

- segment를 통계 기반 embedding으로 변환
- 초기 구현은 deep representation이 아니라 statistical representation이다.

사용 feature 후보:

- `cpu_percent`
- `memory_percent`
- `gpu_percent`
- `gpu_vram_mb`
- `gpu_power_w`
- `disk_read_mb`
- `disk_write_mb`
- `inbound_mb`
- `outbound_mb`
- `external_packet_count`

각 feature별 통계:

- mean
- std
- min
- max
- last
- slope
- p95
- range

예상 함수:

```python
def build_embedding(segment: dict) -> list[float]:
    ...
```

결측값 처리:

- GPU가 없는 PC는 GPU 관련 값을 `0.0`으로 둔다.
- 모든 계산 결과는 finite number여야 한다.
- `NaN`, `inf`, `-inf`는 `0.0`으로 치환한다.

### 4.3 `ml_server/retrieval/retrieval_store.py`

역할:

- 과거 segment와 embedding 저장
- 현재 segment와 유사한 과거 segment top-k 검색
- PC history 삭제 시 retrieval segment도 함께 삭제

초기 저장 구조:

```python
segment_history_by_slot: dict[str, deque] = {
    "class": deque(maxlen=20000),
    "free": deque(maxlen=20000),
}
```

저장 item 예:

```json
{
  "segment_id": "pc-01:class:2026-05-15T10:00:00",
  "pc_id": "pc-01",
  "slot": "class",
  "embedding": [...],
  "verdict": "NORMAL",
  "score": 3.2,
  "context": "class",
  "start_ts": "...",
  "end_ts": "..."
}
```

예상 함수:

```python
def search_similar(segment: dict, embedding: list[float], top_k: int = 3) -> list[dict]:
    ...

def add_segment(segment: dict, embedding: list[float], verdict: str, score: float) -> None:
    ...

def clear_pc(pc_id: str) -> bool:
    ...
```

검색 정책:

- 같은 slot의 segment를 우선 검색한다.
- 자기 PC의 바로 직전 segment만 과도하게 잡히는 것을 막기 위해 필요하면 동일 `segment_id`와 동일 `end_ts`는 제외한다.
- MVP에서는 cosine distance 또는 euclidean distance를 사용한다.

## 5. Evidence Builder 계획

신규 파일:

```text
ml_server/scorer/retrieval_evidence.py
```

역할:

- retrieved cases를 요약한다.
- peer mismatch를 계산한다.
- retrieval score를 산출한다.

예상 함수:

```python
def build_retrieval_evidence(
    current_segment: dict | None,
    retrieved_cases: list[dict],
    peer_latest: dict,
) -> dict:
    ...
```

반환 예:

```json
{
  "available": true,
  "retrieval_score": 2,
  "similar_normal_count": 2,
  "similar_observe_count": 0,
  "similar_suspicious_count": 1,
  "similar_high_risk_count": 0,
  "novelty": false,
  "peer_mismatch": true,
  "same_slot_peer_count": 39,
  "similar_peer_spike_count": 1,
  "top_k": [
    {
      "segment_id": "pc-03:class:2026-05-15T09:31:00",
      "distance": 0.18,
      "verdict": "NORMAL",
      "score": 3.1,
      "pc_id": "pc-03"
    }
  ]
}
```

초기 점수 정책:

| 조건 | 점수 |
|---|---:|
| 유사 NORMAL segment가 top-k의 다수 | -2 |
| 유사 SUSPICIOUS segment 존재 | +2 |
| 유사 HIGH_RISK segment 존재 | +3 |
| 유사 과거 사례 거의 없음 | +1 |
| peer mismatch 있음 | +2 |

점수 제한:

```text
-2 <= retrieval_score <= 5
```

## 6. 기존 파일 수정 계획

### 6.1 `ml_server/api/analyze_router.py`

수정 내용:

- `build_segment`
- `build_embedding`
- `retrieval_store.search_similar`
- `build_retrieval_evidence`
- `retrieval_store.add_segment`

삽입 위치:

```text
predict_anomaly 이후
analyze_pattern 이전
```

최종 저장 위치:

```text
analyze_pattern 이후
agent 실행 이전 또는 이후
```

저장 시 포함할 값:

- `verdict`
- `scores.final`
- `retrieval_evidence`

응답에 추가할 top-level key:

```json
"retrieval_evidence": {...}
```

### 6.2 `ml_server/scorer/verdict_classifier.py`

수정 내용:

- `analyze_pattern()`에 `retrieval_evidence` 선택 인자 추가
- `_build_breakdown()`에 `retrieval` 항목 추가
- `adjusted_score`에 retrieval score 반영

변경 전 breakdown:

```json
{
  "resource": 0,
  "network": 0,
  "process": 0,
  "episode": 0,
  "correlation": 0,
  "ml": 0,
  "context_discount": 0,
  "final": 0
}
```

변경 후 breakdown:

```json
{
  "resource": 0,
  "network": 0,
  "process": 0,
  "episode": 0,
  "correlation": 0,
  "ml": 0,
  "retrieval": 0,
  "context_discount": 0,
  "final": 0
}
```

주의:

- retrieval score는 context discount 전 점수에 반영한다.
- retrieval evidence가 없으면 `retrieval=0`으로 둔다.
- 기존 호출부와 테스트가 깨지지 않도록 인자는 기본값 `None`으로 둔다.

### 6.3 `ml_server/storage/pc_history_store.py`

수정 내용:

현재 `all_pc_latest`는 CPU, memory, timestamp 정도만 저장한다.

peer comparison을 위해 다음 값을 추가 저장한다.

- `slot`
- `inbound_mb`
- `outbound_mb`
- `disk_read_mb`
- `disk_write_mb`
- `gpu_percent`
- `external_packet_count`

### 6.4 `ml_server/agent/claude_api_agent.py`

수정 내용:

- `pattern_result["retrieval_evidence"]`를 읽는다.
- prompt에 `[유사 과거 사례]`, `[Peer 비교]` 섹션을 추가한다.

prompt 포함 정보:

- current segment summary
- top-k retrieved cases
- past verdict
- distance
- peer mismatch
- engine verdict
- score breakdown

주의:

- AI Agent가 verdict를 단독으로 뒤집는 구조로 만들지 않는다.
- Scoring Engine이 verdict를 산출하고, AI Agent는 evidence 기반 설명과 조치 권고를 생성한다.

### 6.5 `ml_server/api/clear_router.py`

수정 내용:

- `retrieval_store.clear_pc(pc_id)` 호출 추가

목적:

- `/history/{pc_id}` 삭제 시 segment retrieval 저장소도 같이 정리한다.

### 6.6 `ml_server/storage/__init__.py`

수정 내용:

- `retrieval_store` export 추가

## 7. 테스트 계획

### 7.1 단위 테스트

신규 테스트 후보:

```text
tests/unit/test_segment_builder.py
tests/unit/test_segment_embedding.py
tests/unit/test_retrieval_store.py
tests/unit/test_retrieval_evidence.py
```

검증 항목:

- snapshot 12개 미만이면 segment 생성 안 됨
- snapshot 12개 이상이면 start/end/window_size가 맞음
- embedding 길이가 고정됨
- embedding 값이 모두 finite number임
- 유사 segment top-k가 distance 오름차순으로 반환됨
- NORMAL 유사 사례가 많으면 retrieval score가 감소함
- HIGH_RISK 유사 사례가 있으면 retrieval score가 증가함
- peer mismatch가 있으면 retrieval score가 증가함

### 7.2 통합 테스트

수정 대상:

```text
tests/integration/test_response_schema.py
```

변경 항목:

- top-level `retrieval_evidence` 필수 key 추가
- `score_breakdown` expected key에 `retrieval` 추가

신규 테스트 후보:

```text
tests/integration/test_retrieval_augmented_analyze.py
```

검증 항목:

- `/analyze` 응답에 `retrieval_evidence`가 존재함
- 충분한 segment가 쌓인 뒤 top-k가 반환됨
- `scores.score_breakdown.retrieval`이 존재함
- `scores.final`이 retrieval score를 반영함
- `agent.reason` 또는 prompt mock에 retrieved evidence가 포함됨

### 7.3 회귀 테스트

검증 항목:

- retrieval evidence가 없는 초기 구간에서도 `/analyze`가 정상 응답함
- 기존 IF/LOF unavailable 흐름이 깨지지 않음
- 기존 NORMAL/OBSERVE/SUSPICIOUS/HIGH_RISK enum이 유지됨
- `/history/{pc_id}` 호출 후 retrieval segment가 삭제됨

## 8. 성능 영향 분석

### 8.1 예상 데이터 규모

40대 PC, 5초 수집, 1분 segment 기준:

```text
40 PCs × 8 hours × 60 segments/hour × 7 days
= 13,440 segments
```

이 규모는 메모리 기반 linear search로도 MVP 구현이 가능하다.

### 8.2 예상 비용

- segment 생성: 최근 12개 snapshot 통계 계산, 매우 낮음
- embedding 생성: feature 수 × 통계 수 계산, 낮음
- retrieval 검색: segment 수 × embedding dimension 거리 계산
- AI prompt 증가: top-k 3개 수준이면 token 증가 작음

### 8.3 제한 정책

- slot별 segment 저장 개수 제한: `maxlen=20000`
- top-k 기본값: `3`
- retrieval score 범위 제한: `-2` to `5`
- prompt에는 top-k 전체 raw snapshot을 넣지 않고 summary만 넣는다.

### 8.4 확장 계획

MVP 이후 segment가 많아지면 다음 중 하나로 교체한다.

- `sklearn.neighbors.NearestNeighbors`
- FAISS
- PostgreSQL `pgvector`

## 9. 검증 지표

논문 반영을 주장하려면 기능 구현만으로 부족하다.

최소 검증 지표:

| 지표 | 설명 |
|---|---|
| false positive count | 정상 데이터에서 OBSERVE 이상으로 나온 횟수 |
| false positive rate | 정상 데이터 전체 중 오탐 비율 |
| retrieval coverage | 분석 건수 중 top-k 검색이 가능했던 비율 |
| peer mismatch count | 단독 이상으로 판단된 횟수 |
| verdict change count | retrieval 적용으로 verdict가 바뀐 횟수 |

비교 방식:

```text
baseline: rule + IF/LOF + context
candidate: rule + IF/LOF + retrieval + context
```

성공 기준 예:

```text
정상 데이터 기준 false positive rate 10% 이상 감소
HIGH_RISK 누락 증가 없음
retrieval coverage 70% 이상
```

## 10. 구현 순서

권장 순서:

1. `segment_builder.py` 추가
2. `segment_embedding.py` 추가
3. `retrieval_store.py` 추가
4. `retrieval_evidence.py` 추가
5. `analyze_router.py`에 retrieval 흐름 연결
6. `verdict_classifier.py`에 retrieval score 반영
7. `claude_api_agent.py` prompt에 evidence 추가
8. `clear_router.py`에서 retrieval 저장소 삭제 처리
9. unit test 추가
10. integration test 수정 및 추가
11. 정상 데이터 기준 오탐 감소 리포트 작성

## 11. 완료 기준

아래 조건을 모두 만족해야 논문 핵심 구조 반영으로 볼 수 있다.

- 현재 metric window가 segment로 생성된다.
- segment embedding이 생성된다.
- 과거 segment top-k 검색 결과가 실제로 반환된다.
- retrieval score가 `score_breakdown.retrieval`에 들어간다.
- retrieval score가 `scores.final`과 verdict에 영향을 줄 수 있다.
- `/analyze` 응답에 `retrieval_evidence`가 포함된다.
- AI Agent prompt에 retrieved cases와 peer comparison이 포함된다.
- 정상 데이터 기준 오탐 감소가 수치로 확인된다.

## 12. 금지 사항

다음 방식은 논문 반영으로 보지 않는다.

- prompt에 "과거와 비교했다"는 문장만 추가
- segment 저장 없이 LLM 설명만 변경
- embedding 없이 단순 최근 값만 비교
- top-k 검색 결과 없이 retrieval score를 하드코딩
- retrieval score가 final score에 영향을 주지 않음
- 검증 지표 없이 기능 설명만 추가

## 13. 보고서 표현 가이드

정확한 표현:

> 본 프로젝트는 해당 논문의 전체 모델을 재현하지 않고, 핵심 구조인 시계열 segment 기반 유사 사례 검색과 retrieval-augmented LLM explanation을 RADA 환경에 맞게 적용하였다. 초기 구현은 statistical window embedding과 top-k retrieval을 사용하며, 검색 결과는 이상 점수와 AI Agent 설명 근거에 직접 반영된다.

피해야 할 표현:

> Deep Feature-Based Time Series Similarity를 완전 구현하였다.

이 표현은 TS2Vec, T-Rep, 1D-CNN encoder 등 실제 deep representation model이 들어가기 전까지 사용하지 않는다.
