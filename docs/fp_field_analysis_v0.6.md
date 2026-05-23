# RADA Field Analysis — Severity Promotion & FP Sources (v0.6.0)

본 문서는 RADA scoring v0.6.0 적용 후 본인 PC 에서 2일 13시간 (`2026-05-20 16:26` ~ `2026-05-23 05:32`) 동안 수집한 정상 사용 데이터를 기반으로, 어떤 신호가 어떤 severity 로 올라가는지, 그리고 어디서 FP 가 발생하는지를 정량 분석한다.

**핵심 결론**: 현재 `anomaly_history` 의 `severity` 가 너무 쉽게 올라간다. 단일 신호 (alert 1개) 만으로 MEDIUM 진입이 948건, `engine verdict ≠ severity` 불일치가 707건. 알고리즘 본질의 점수 + verdict 결정 로직에 gating 보강이 필요.

---

## 1. Setup

| 항목 | 값 |
|---|---|
| PC | `0c7a15737f66` (admin lab notebook, 정상 사용) |
| 수집 기간 | `2026-05-20 16:26 ~ 2026-05-23 05:32` (≈ 2일 13시간 06분) |
| `metrics_history` row 수 | **7,364** |
| Scoring policy | `scoring-v0.6.0` (category gating 활성, correlation 약화 4건 반영) |
| Mining trigger 발생 횟수 | 0 (mining 시뮬레이션 안 함, 순수 정상 사용 기간) |
| 사용 패턴 추정 | dev (Docker compose 빌드 / pytest), 게임 업데이트 / 플레이 추정 (5/22 03:57 / 04:14 시점 spike) |

---

## 2. Anomaly History 분포 (전체)

| severity | anomaly_type | count |
|---|---|---|
| LOW    | OBSERVE     | **3,330** |
| MEDIUM | SUSPICIOUS  | 563 |
| MEDIUM | NORMAL      | 404 |
| MEDIUM | OBSERVE     | 347 |
| HIGH   | OBSERVE     | **155** |
| HIGH   | SUSPICIOUS  | 46 |
| HIGH   | HIGH_RISK   | 5 |
| HIGH   | NORMAL      | 3 |

**합계 anomaly_history**: 4,853 / metrics_history 7,364 = **65.9%**

→ 정상 사용 7,364 metric 중 4,853 (65.9%) 이 anomaly_history 에 기록됨. 운영 알람 가시화 시 학생 PC 40대 × 8시간 = 320 PC-시간 동안 수천 건 알람 폭주.

---

## 3. 본질 문제 — Severity 와 Verdict 불일치 707건

`severity` (top-level) 와 `anomaly_type` (engine verdict) 가 서로 다른 경우. 정책상 일관성이 깨진 상태.

### 3-A. MEDIUM/NORMAL: 404건 (final_score=0 인데도 저장)

```
MEDIUM/NORMAL 의 단일 alert:
  LOCAL_HW_CPU_DEGRADATION  ← 308 건  (76%)
  LOCAL_MEM_HIGH            ← 89  건  (22%)
  LOCAL_CPU_HIGH            ← 7   건  (2%)
```

→ Engine verdict 는 NORMAL (`final_score = 0`) 인데 local alert 의 `severity=MEDIUM` 이 top-level severity 를 강제로 MEDIUM 으로 올림. 정상 PC 의 메모리 85%+ / CPU degradation 단순 감지를 incident 로 저장하는 셈.

**비고**: `LOCAL_HW_CPU_DEGRADATION` 이 본인 분석에서 누락된 큰 주범 — 308건. 단순 CPU 히스토리 통계로 "노후화" 의심 → 정상 dev burst 가 트리거.

### 3-B. HIGH/OBSERVE: 155건 (verdict OBSERVE 인데 HIGH 승격)

```
HIGH/OBSERVE 의 첫 alert type:
  OBSERVE_BACKDOOR    59 건  (38%)
  OBSERVE_MEMORY      53 건  (34%)
  OBSERVE_GPU_MINING  22 건  (14%)
  DOS_SUSPECTED       10 건  (6%)
  OBSERVE_STEALTH     6  건  (4%)
```

→ Engine verdict 는 `OBSERVE` (낮은 의심) 인데 alert 중 하나의 `severity=HIGH` 가 top-level 를 HIGH 로 강제 승격. 관제 화면에서 `severity=HIGH` 라는데 verdict 가 OBSERVE 라 운영자가 의미 해석 불가.

### 3-C. HIGH/NORMAL: 3건 (final_score=0, severity HIGH)

극단 케이스. 거의 무관하지만 시스템 일관성 측면에서 0 이어야 정상.

---

## 4. Alert Count 분포 — "단일 신호로 MEDIUM 진입" 정량

```
MEDIUM:
  alert 1개  ← 948 건  (74%)   ★ 압도적
  alert 2개     280 건  (22%)
  alert 3개      57 건  (4%)
  alert 4개      29 건  (2%)

HIGH:
  alert 2개      26 건  (12%)
  alert 3개      38 건  (18%)
  alert 4개      48 건  (23%)
  alert 5개      97 건  (46%)   ← 다수 신호 동시
```

→ **MEDIUM 의 74% 가 alert 단 1개로 진입**. HIGH 는 다수 신호 동시 발화가 다수 (5개 alert 가 46%) — HIGH 자체 신뢰도는 상대적으로 높지만, severity-verdict 불일치 (3-B) 가 문제.

---

## 5. Top Alert 빈도 (전체 anomaly_history)

```
OBSERVE_BEHAVIOR              3,554
LOCAL_HW_CPU_DEGRADATION        740
SUSPICIOUS_BACKDOOR             575
LOCAL_MEM_HIGH                  253
LOCAL_HW_MEM_DEGRADATION        155
OBSERVE_BACKDOOR                140
LOCAL_MEM_CRITICAL              134
LOCAL_ABSOLUTE_MEM               91
LOCAL_GPU_HIGH                   62
OBSERVE_MEMORY                   53
LOCAL_ABSOLUTE_GPU               46
OBSERVE_STEALTH                  36
DOS_SUSPECTED                    26
OBSERVE_GPU_MINING               26
SUSPICIOUS_EXFIL                 18
OBSERVE_EXFIL                    15
LOCAL_CPU_HIGH                    9
SUSPICIOUS_STEALTH                8
SUSPICIOUS_DOS                    4
OBSERVE_DOS                       4
```

`LOCAL_*` (client 측 local alert) 가 1,490건 (30%+) — 단순 임계 초과만으로 발생. `OBSERVE_BEHAVIOR` 3,554건은 모든 LOW severity 에 자동 발화 (의미 약함).

---

## 6. Trigger Context — 게임 업데이트 / 플레이 가설

DB 재확인 결과 최고 위험 spike 5건은 모두 **2026-05-23** 새벽 (자정 이후) 시점이다. anomaly_type=HIGH_RISK 5건 전부 다음 두 시점에 집중:

```
2026-05-23 03:58:07
  → final = 14.0, alert_count = 4
  - memory 95~96%
  - gpu_active
  - unknown_process_active
  - net_external_high
  - ml_anomaly
  - stealth_mismatch_power

2026-05-23 04:14:21 ~ 04:14:36  (5초 간격 4건 연속)
  → final = 14.33 → 15.27 (점진 상승)
  - inbound 급증
  - dos_spike
  - persistent_ext
  - spike_count_1m
```

→ 자정 이후 게임 업데이트 / 플레이 동시 발생 추정 시나리오:
- GPU 풀가동 + 메모리 95% + 외부 통신 large download + 알 수 없는 process (게임 launcher)
- 이게 mining 패턴과 통계적으로 거의 동일하게 보임

운영상 의미: **고사양 게임 / 대용량 다운로드는 본 시스템에서 mining 과 구분 불가**. 학생 PC 가 게임 가능 환경이라면 야간 FP 폭주.

---

## 7. 개선 제안 (우선순위 순)

### P0-1: LOW / OBSERVE 통합 — 저장 정책 변경

```
현재: LOW/OBSERVE 3,330 건이 anomaly_history 에 저장됨
변경: LOW/OBSERVE 는 anomaly_history 저장 안 함
      대신 weak signal 카운터 또는 summary 로만 유지
```

**효과**: anomaly_history 총량 4,853 → 1,523 (3,330 감소, 68.6% 압축). 운영 알람 가시화 노이즈 대폭 감소.

**구현 — 2단계 권장 (side effect 최소화)**:

1차 (먼저, 안전):
- `server-spring/.../service/AlertService.java` 에서 `verdict=OBSERVE AND severity=LOW` 인 경우 anomaly_history 저장 skip
- ML 응답 형식은 그대로 — `LOW/OBSERVE` 라는 결과 자체는 계속 받음 (운영자 디버그용)

2차 (1차 검증 후):
- ML 응답에 `should_persist: false` 플래그 추가 (verdict=OBSERVE & severity=LOW 시)
- Spring 이 이 플래그를 존중 — 명시적 contract 화

→ 1차만 적용해도 3,330건 즉시 정리. ML verdict 결정 자체를 건드리지 않으므로 다른 영역 (점수, retrieval, 카테고리 게이팅) 회귀 0. 2차는 운영 한 학기 후.

### P0-2: Severity ↔ Verdict 매핑 일관성 강제

현재 불일치 707 건 (MEDIUM/NORMAL 404 + MEDIUM/OBSERVE 347 일부 + HIGH/OBSERVE 155 + HIGH/NORMAL 3).

```
새 정책 (verdict 가 진실, severity 는 derived):
  verdict = NORMAL     → severity = NORMAL    (저장 안 함, P0-1)
  verdict = OBSERVE    → severity ≤ LOW       (저장 안 함, P0-1)
  verdict = SUSPICIOUS → severity = MEDIUM
  verdict = HIGH_RISK  → severity = HIGH
  fast-path mining_known 또는 confirmed mining → severity = HIGH 단독 허용
```

Local alert 의 `severity=HIGH` 가 top-level severity 를 강제 승격하는 경로 제거. Local alert 는 **evidence 만** 남고 verdict 결정에 영향 X.

**효과**: MEDIUM/NORMAL 404 + HIGH/OBSERVE 155 = **559건 즉시 정리**.

**구현 위치**:
- `ml_server/scorer/verdict_classifier.py` — overall_severity 결정 시 verdict 만 참조
- `server-spring/.../service/AlertService.java` — local alert severity 가 ml severity 를 override 못 하게

### P0-3: 승격 Gating 도입 (sustained + signal count)

현재 alert 1개로 MEDIUM 진입 948건. Gating 신규 조건:

```
MEDIUM 진입 조건:
  final_score ≥ medium_threshold  (기존)
  AND active_signal_count ≥ 3
  AND category_count ≥ 2

HIGH 진입 조건:
  final_score ≥ high_threshold  (기존)
  AND active_signal_count ≥ 4
  AND category_count ≥ 2
```

#### Fast-path 예외 (필수)

기계적 gating 만 적용하면 **단순하지만 명확한 mining 을 놓칠 수 있다**. 다음 fast-path 들은 신호 수 / 카테고리 수 무관하게 즉시 HIGH 로 분류:

| Fast-path | 근거 | signal_count 1~2 라도 즉시 HIGH |
|---|---|---|
| **Known miner process** | `process_name ∈ {xmrig, nanominer, t-rex, lolminer, ...}` allowlist 외 | ✓ |
| **Mining pool port + process** | port 3333/4444/7777/... + 외부 IP | ✓ |
| **Suspicious path + outbound** | `/tmp`, `%TEMP%`, `%APPDATA%\Local\Temp` 실행 + 외부 통신 | ✓ |
| **Confirmed mining sustained** | v0.6 의 category gating 3 카테고리 + 3h | ✓ |
| **Cmdline 의 `stratum+tcp`** | Stratum 프로토콜 명시 | ✓ |

→ Gating 은 **stealth mining / 이름 위장 mining** 에만 적용. 명백한 mining 시그니처는 그대로 즉시 HIGH.

**효과**: 단일 신호 trigger 차단. MEDIUM 948건 중 alert 1개 케이스는 LOW 로 강등 또는 미저장. Fast-path 보존으로 mining 탐지력 유지.

**구현 위치**:
- `ml_server/scorer/verdict_classifier.py` — 분류 직전 gating check 추가
- `ml_server/config_yaml/scoring_policy.yaml` v0.7 — gating 임계 정의 + fast-path 예외 명시

#### evidence_meta 응답 구조 (운영 / 검증용)

지금은 alert.detail 안에 `활성신호=[...]` 문자열로 들어가 있어 SQL 로 파싱 어려움. Gating 도입과 함께 **응답 top-level 에 구조화된 evidence_meta** 추가 권장:

```json
{
  "scores": { ... },
  "category_signals": { ... },
  "evidence_meta": {                                    // ← NEW
    "active_signal_count": 5,
    "category_count": 3,
    "active_categories": ["resource", "network", "ml"],
    "active_signals": ["cpu_flat", "net_out_sustained", "gpu_high", "mem_high", "ml_anomaly"],
    "promotion_gated": true,
    "promotion_reason": "signal_count>=3 AND category_count>=2",
    "fast_path_match": null
  }
}
```

→ Spring 이 이걸 `anomaly_history.scores` 의 `evidence_meta` 키로 보존하면, Grafana 가 단순 SQL 로:
- "지난 24h gating 발화한 anomaly 비율"
- "active_categories 분포"
- "fast-path 발화 카운트 vs gating 발화 카운트"

같은 정량 분석이 가능. 발표 시 "왜 이 anomaly 가 HIGH 인가" 설명에 직접 활용.

**구현 위치**:
- `ml_server/api/analyze_router.py` — 응답 형식 확장
- `server-spring/.../dto/MlResponse.java` — `evidenceMeta` 필드 추가
- `server-spring/.../service/AlertService.java` — scores JSONB 에 병합 (R1, category_signals 와 동일 패턴)

#### ⚠️ Gating 도입 부작용 — score 와 verdict 의 분리

P0-3 가 적용된 후 **`scores.final` 은 원래 점수를 유지하지만, gating 차단 시 verdict / overall_severity 는 낮아진다**. 예시:

| 케이스 | scores.final | verdict | overall_severity | evidence_meta.promotion_gated |
|---|---|---|---|---|
| 정상 mining 탐지 (4 signals, 2 categories) | 14.5 | HIGH_RISK | HIGH | false |
| 단일 신호 burst (1 signal) | 12.0 | OBSERVE | LOW | **true** |
| Fast-path (xmrig) | 22.0 | HIGH_RISK | HIGH | false (`fast_path:mining_known`) |

→ **점수가 12 인데 severity 가 LOW** 인 경우가 정상 동작 (gating 의도). 감사 관점은 OK 지만, **대시보드 / 운영 화면에서 `scores.final` 만 보면 운영자가 혼란**.

**필수 룰 — Grafana 패널 / 운영 SQL 작성 시**:

1. **`scores.final` 표시하는 모든 패널**은 동일 row 의 `scores.evidence_meta.promotion_gated` 와 `promotion_reason` 을 함께 노출 (table column / tooltip / 색상 등)
2. **점수 정렬/필터 패널**은 `promotion_gated = false` 조건으로 정렬 또는 별도 카테고리 분리
3. **PC 별 위험도 ranking** 같은 패널은 verdict 우선 (HIGH_RISK / SUSPICIOUS / OBSERVE / NORMAL) 정렬 후 `scores.final` 은 보조 지표

Grafana 패널 예시 (권장 SQL):
```sql
SELECT
  pc_id,
  detected_at,
  severity,
  anomaly_type AS verdict,
  scores->>'final' AS raw_score,
  -- 운영자 시점: gated 여부 + 사유 같이 보여주기
  scores->'evidence_meta'->>'promotion_gated' AS gated,
  scores->'evidence_meta'->>'promotion_reason' AS reason,
  scores->'evidence_meta'->>'fast_path_match'  AS fast_path
FROM pc_monitor.anomaly_history
WHERE detected_at > NOW() - INTERVAL '1 hour'
ORDER BY
  CASE severity
    WHEN 'HIGH'   THEN 0
    WHEN 'MEDIUM' THEN 1
    WHEN 'LOW'    THEN 2
    ELSE 3 END,
  (scores->>'final')::float DESC;
```

→ `promotion_gated = true` 인 row 가 점수 높아도 severity LOW 라는 게 표 한 줄로 명확히 보임.

### P1-1: Local Alert → Evidence Only

```
현재: local alert (LOCAL_MEM_HIGH 등) 가 anomaly_history.severity 결정
변경: local alert 는 scores.evidence[].local_alerts 로 보존만,
       severity / verdict 결정은 ML engine output 만 사용
```

**효과**: P0-2 와 결합. MEDIUM/NORMAL 의 LOCAL_HW_CPU_DEGRADATION 308 + LOCAL_MEM_HIGH 89 = **397건 모두 NORMAL/저장 안 함** 으로 정리.

**구현 위치**:
- `server-spring/.../service/AlertService.java` — local alert 합산 로직 제거 또는 evidence 로 분리
- 응답 형식에 `local_evidence` 추가 (top-level 별도 키)

### P1-2: DOS / Network Spike 절대값 Floor

```
현재: inbound spike 평균 대비 N배 비율로 dos_spike
문제: baseline 0.03 MB 일 때 2.5 MB = 80배 비율 → false dos 발화
변경: dos_spike 조건에 절대값 floor 추가
  relative_ratio ≥ 15
  AND inbound_mb ≥ 20 MB / 5s
  AND 지속 N회
```

**효과**: 게임 다운로드 / 일반 video streaming 의 burst 가 dos_spike 로 잡히는 케이스 차단. `DOS_SUSPECTED 26건 + LOCAL_HW_MEM_DEGRADATION 155건` 의 일부 정리.

**구현 위치**:
- `ml_server/scorer/signal_extractor.py` — dos / network spike 신호 조건에 absolute_min 추가
- `scoring_policy.yaml` — `dos_min_inbound_mb_per_5s: 20.0` 같은 키 추가

### P1-3: Episode Score Decay / Cooldown

현재: episode=7 같은 큰 점수가 한 번 튀면 수십 초간 유지 → 같은 원인 anomaly 가 5초마다 수십~수백 건 누적

```
변경:
  - 정상 window 가 N회 (예: 12 = 1분) 연속 나오면 episode score 빠르게 0 으로 decay
  - 같은 alert type 이 cooldown (예: 60초) 동안 중복 저장 시 skip 또는 1건으로 dedupe
```

**효과**: spike 1회당 anomaly_history 1건 (또는 시작/지속/종료 3건) 으로 압축.

**구현 위치**:
- `ml_server/scorer/signal_extractor.py` — episode_state 관리
- `ml_server/storage/pc_history_store.py` — last alert type per PC 보관 + dedupe window

### P1-4: Retrieval Positive Score Gating

현재: retrieval=3~5 가 다른 약한 신호와 합쳐져 승격 기여 가능

```
변경:
  - retrieval positive score (+3 ~ +5) 는 단독으로 verdict 승격 못 함
  - retrieval ≥ 3 일 때 category_count ≥ 2 도 함께 만족해야 점수 반영
  - 그 외엔 retrieval 점수 0 (또는 evidence only)
```

**효과**: retrieval 의 borderline 보강 효과는 유지하되, retrieval 단독으론 MEDIUM 승격 못 함.

**구현 위치**:
- `ml_server/scorer/verdict_classifier.py` — retrieval 점수 합산 직전 gating check
- 또는 `ml_server/retrieval/retrieval_evidence.py` — gating 만족 시만 positive score 반환

---

## 8. 우선순위 / 구현 작업 순서

| 순서 | 작업 | 영향 (예상 row 정리) | 작업량 | Risk |
|---|---|---|---|---|
| **P0-1** LOW/OBSERVE 저장 안 함 (Spring filter 1차) | server-spring AlertService 1파일 | **3,330 (68.6%)** | 30분 | **낮음** (저장만 안 함, ML/scorer 무변경) |
| **P0-2** Severity ↔ Verdict 매핑 강제 | ML + Spring 2파일 | 559건 (HIGH/OBSERVE 155 + MEDIUM/NORMAL 404) | 1시간 | 중간 (verdict 결정 로직 변경) |
| **P0-3** 승격 Gating (signal_count + category_count) + evidence_meta | scorer + policy.yaml + DTO 전파 | MEDIUM 948건 중 다수 | 2시간 (evidence_meta 포함) | 중간 (fast-path 예외 필수, 측정 필수) |
| P1-1 Local alert → evidence only | Spring AlertService + 응답 형식 | 397건 (P0-2 와 부분 중복) | 1시간 | 낮음 |
| P1-2 DOS / spike 절대값 floor | scorer + policy.yaml | DOS_SUSPECTED 의 절반 추정 | 30분 | 낮음 |
| P1-3 Episode decay / dedupe | scorer + pc_history_store | spike 당 수십 건 → 1~3건으로 압축 | 1.5시간 | 중간 (dedupe 로직 복잡) |
| P1-4 Retrieval positive gating | verdict_classifier 또는 retrieval_evidence | retrieval 단독 승격 케이스 차단 | 30분 | 낮음 |

**총 작업량**: P0 3건 = 약 3.5시간 → 정상 사용 시 anomaly 4,853 → 약 600~800 (85%↓) 예상.

### 권장 머지 순서

1. **P0-1 (Spring filter only) 먼저 작은 PR** — 3,330건 즉시 정리, ML 무변경이라 안전. 며칠 정상 데이터로 회귀 확인.
2. **P0-2 별도 PR** — ML + Spring 양쪽 변경. P0-1 적용 후 안정 상태에서 진행해야 회귀 추적 쉬움.
3. **P0-3 + evidence_meta 한 PR** — Gating 과 그 근거 데이터 같이 도입. 테스트로 fast-path 예외 검증 후 머지.
4. P1 항목들은 P0 검증 끝나면 개별 PR.

**작은 단위로 자주 머지**: P0-1 → P0-2 → P0-3 각각 별도 PR + 본인 PC 4h 측정 첨부.

---

## 9. 측정 / 검증 방법 (P0 적용 후)

1. 본인 PC 에서 동일 정상 사용 패턴 4시간+ 수집
2. anomaly_history 분포 재측정 — 본 문서 §2 표와 비교
3. 진짜 mining 시나리오 (`tools/anomaly_trigger.py`) 가 여전히 HIGH 잡는지 확인
4. severity-verdict 불일치 0 확인
5. MEDIUM 의 alert 1개 케이스 0 (또는 minimal) 확인

**기대 목표**:
- LOW/OBSERVE 저장 0
- MEDIUM/NORMAL 0
- HIGH/OBSERVE 0
- HIGH/NORMAL 0
- 정상 사용 시 anomaly_history 총량 < 1,000 (현재 4,853 의 20% 이하)
- mining 시뮬레이션은 100% HIGH/HIGH_RISK 유지

---

## 10. 한계 / 미해결

### 본 데이터의 한계
- 단일 PC, 단일 사용자 패턴 (dev + 게임 추정)
- mining 동시 시뮬레이션 없음 — 본 데이터로는 "위 개선안이 진짜 mining 을 놓치는지" 검증 불가
- 학교 lab 환경 PC 의 사용 패턴 (학년/시간대 분포) 미반영

### 구현 시 주의사항
- P0-3 의 signal_count / category_count gating 은 **단순 mining 도 놓칠 수 있음**. fast-path (mining_known process+port) 예외 보존 + 운영 한 학기 측정 후 보정 필수
- P1-3 의 dedupe 는 **동일 원인 반복 spike** (예: 같은 사용자가 같은 게임 반복 실행) 가 한 번에 한 건으로 압축되므로 의도는 맞지만, **새 사고 발생을 못 잡는 위험**도 있음. cooldown 종료 후 재발화 보장 필요.

### 다음 측정 직전 확인할 것

#### LOCAL_HW_CPU_DEGRADATION — 별도 점검 필수 (308건 출처)

`client_core/detector/hw_degradation.py` 의 발화 조건이 정상 dev burst 에도 거의 무조건 뜨는 구조라면:

- **P0-2 (local alert → evidence only) 만으론 부족** — alert 가 evidence 로 옮겨가도 매 5초마다 발화하면 evidence_meta 가 noise 로 가득 참
- **신호 자체 약화** 필요: 발화 임계 조건에 sustained 추가 (예: "CPU history 30분+ 일정 패턴 + 평소 baseline 대비 일정 deviation" 등)
- 또는 **신호 비활성화** + 별도 PC 노후화 monitor (별도 dashboard) 로 분리

이 점검은 P0 작업 시작 직전 별도 5~10분 분량의 작은 task. `hw_degradation.py` 의 발화 조건 + 5/22 ~ 5/23 의 740건 분포 확인.

---

## 부록 — 본 분석 쿼리 (재현 가능)

```sql
-- §2 severity x verdict
SELECT severity, anomaly_type, COUNT(*)
FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66'
GROUP BY severity, anomaly_type
ORDER BY COUNT(*) DESC;

-- §3-A MEDIUM/NORMAL drill-down
SELECT alerts->0->>'type' AS only_alert, COUNT(*)
FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66'
  AND severity='MEDIUM' AND anomaly_type='NORMAL'
GROUP BY only_alert
ORDER BY COUNT(*) DESC;

-- §3-B HIGH/OBSERVE drill-down
SELECT alerts->0->>'type' AS first_alert, COUNT(*)
FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66'
  AND severity='HIGH' AND anomaly_type='OBSERVE'
GROUP BY first_alert
ORDER BY COUNT(*) DESC;

-- §4 alert count 분포
SELECT severity, jsonb_array_length(alerts) AS alert_count, COUNT(*)
FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66'
  AND severity IN ('MEDIUM','HIGH')
GROUP BY severity, alert_count
ORDER BY severity, alert_count DESC;

-- §5 top alert
SELECT alert->>'type' AS alert_type, COUNT(*) AS cnt
FROM pc_monitor.anomaly_history,
     jsonb_array_elements(alerts) AS alert
WHERE pc_id='0c7a15737f66'
GROUP BY alert_type
ORDER BY cnt DESC
LIMIT 20;
```

---

**다음 액션** (코드 변경 전 가벼운 확인):
- `client_core/detector/hw_degradation.py` 의 LOCAL_HW_CPU_DEGRADATION 발화 조건 확인
- `server-spring/.../service/AlertService.java` 의 severity 결정 로직 확인 — local alert 와 ML verdict 우선순위
- 두 곳이 P0 작업의 핵심 변경 지점.
