# RADA Post-P0/P1 Field Verification

P0 (3건) + HW threshold 강화 + P1 (4건) 적용 후 동일 호스트 / 동일 사용 패턴으로 4시간 38분 재측정한 결과. 본 문서는 `docs/fp_field_analysis_v0.6.md` 의 후속.

**핵심 결론**: anomaly_history 생성률이 **65.9% → 1.6% (41× 감소)**. severity-verdict 불일치 707건 → 0건. 운영 알람 폭주 문제 사실상 해소.

---

## 1. Setup

| 항목 | Pre-P0/P1 (베이스라인) | Post-P0/P1 (이번 측정) |
|---|---|---|
| PC | `0c7a15737f66` | 동일 |
| 사용 패턴 | dev + 추정 게임 | 동일 (dev + 추정 게임/streaming) |
| 수집 기간 | 2일 13시간 | 4시간 38분 |
| Scoring policy version | `scoring-v0.6.0` | **`scoring-v0.8.0`** (P0+P1+HW) |
| Split point | — | `2026-05-24 15:12:07.93+09` (이 시점 이전 데이터는 분석 제외) |

적용된 PR (split point 이후 효력):
- `3e88ddb` P0-1 LOW/OBSERVE skip
- `b571a31` P0-2 verdict → severity 매핑
- `d979cdd` P0-3 promotion gating + evidence_meta
- `70cf2e9` HW degradation threshold 1.3→2.0 + baseline floor 30/50
- `2d252ee` P1 묶음 (local_evidence / DOS floor / episode decay / retrieval gating)
- `a9e53e5` Spring AlertService `@Autowired` + postgres host port

---

## 2. 핵심 수치 비교

| 지표 | Pre-P0/P1 (4,853 anomaly @ 2일13h) | Post-P0/P1 (54 anomaly @ 4h38m) | 변화 |
|---|---|---|---|
| metrics_history rows (분석 구간) | 7,364 | 3,343 | — |
| anomaly_history rows | **4,853** | **54** | — |
| anomaly / metrics ratio | **65.9%** | **1.6%** | **41× 감소** |
| 시간당 anomaly 평균 | ~80 / 시간 | ~12 / 시간 | 6.7× 감소 |
| 40대 PC × 8시간 추정 알람 | ~25,600 | ~3,840 | 6.7× 감소 |

운영 수용 가능 수준 — 학생 PC 40대 환경에서 하루 단위 알람 약 100~400건 수준.

---

## 3. severity × verdict 분포

### Pre-P0/P1
```
LOW    / OBSERVE      3,330  (68.6%)
MEDIUM / SUSPICIOUS     563  (11.6%)
MEDIUM / NORMAL         404  (8.3%)
MEDIUM / OBSERVE        347  (7.2%)
HIGH   / OBSERVE        155  (3.2%)
HIGH   / SUSPICIOUS      46  (0.9%)
HIGH   / HIGH_RISK        5  (0.1%)
HIGH   / NORMAL           3  (0.06%)
```

### Post-P0/P1
```
MEDIUM / SUSPICIOUS      54  (100%)
```

→ **불일치 0건**. LOW/OBSERVE 3,330건 + MEDIUM/NORMAL 404건 + HIGH/OBSERVE 155건 (총 3,889 = 80%) 이 모두 정리됨.

---

## 4. P0-3 Gating 동작 검증

`evidence_meta.promotion_gated` / `promotion_reason` / `fast_path_match` 분포:

| gated | fast_path | reason | count |
|---|---|---|---|
| false | (null) | gating_passed | **54** |

→ **54건 모두 정당하게 gating 통과**. signal count + category count 동시 충족. gating 차단 (gated=true) 사례 0건 — 본 측정 구간엔 "단일 신호 burst" 가 한 번도 없었음 (P1 의 cooldown / HW threshold / DOS floor 등이 이미 막아서).

### signal_count × category_count 분포

| signals | categories | count |
|---|---|---|
| 7 | 6 | 27 |
| 9 | 7 | 21 |
| 7 | 5 | 3 |
| 9 | 6 | 1 |
| 9 | 5 | 1 |
| 5 | 5 | 1 |
| 4 | 6 | 1 |

→ 최소 4 signals + 5 categories 동시 만족. 단일 신호 / 단일 카테고리로 진입한 row 0건 — P0-3 의 핵심 보장 작동.

---

## 5. Alert type 분포

| type | count | 이전 측정 |
|---|---|---|
| SUSPICIOUS_BACKDOOR | **53** | (P0-2 전: 575 + OBSERVE_BACKDOOR 140) |
| SUSPICIOUS_EXFIL | **2** | (P0-2 전: 18 + OBSERVE_EXFIL 15) |

LOCAL_* 자체가 발화 안 됨 — HW threshold 강화 + P1-1 (local_evidence 분리) 효과. `scores.local_evidence` 보존 컬럼 54건 모두 null = 이번 측정 동안 학생 PC 의 client 가 local alert 자체를 안 발생시킴 (정상 dev burst 가 새 ratio 2.0 + baseline floor 30/50 을 못 넘김).

---

## 6. P1-3 Cooldown 동작 검증

동일 anomaly_type 사이 시간 간격:

| anomaly_type | rows | min_gap | avg_gap |
|---|---|---|---|
| SUSPICIOUS | 54 | **00:01:00.002s** | 2분 7초 |

→ **최소 간격 60.002 초** — 60초 cooldown 정확히 작동. 5초 간격으로 spike 가 떠도 1분당 1건만 저장.

이전 측정에서 5초 간격으로 SUSPICIOUS 가 수십~수백 건 누적되던 행동이 완전히 압축됨.

---

## 7. 시간 분포

| hour | count |
|---|---|
| 15:00 ~ 17:00 | 0 |
| 17:00 | 2 |
| 18:00 | 29 |
| 19:00 | 24 (~19:51 까지) |

→ 첫 두 시간 (15~17시) 동안 SUSPICIOUS 0건 — 정상 dev 작업만 했을 때. 17시 이후 burst 시작 (게임 / 스트리밍 / 무거운 dev 작업 추정). burst 발생 시간대에 cooldown + gating 덕에 분당 0.2건 수준 유지.

---

## 8. SUSPICIOUS_BACKDOOR 53건 분석

본 측정에서 유일한 알람 유형. 정상 사용 중 어떤 행위가 backdoor 패턴으로 분류됐는지 별도 점검 필요.

활성 신호 추정 (build_alerts 로직 + 이전 분석 기반):
- `net_external_high` — chrome / discord / OneDrive 등 외부 통신
- `exec_path_suspicious` — `%APPDATA%\Local` 거주 앱 (chrome, vs code)
- `persistent_ext` — long-running 외부 endpoint (cloud sync / IDE LSP)
- `outbound_spike` — 게임 다운로드 / 동영상 스트리밍

이 조합이 4+ signals × 5+ categories 충족해서 P0-3 gating 도 통과 — 알고리즘적으론 정당함. **그러나 정상 dev/사용 환경의 자연스러운 패턴** 이라 운영상 FP 일 가능성 큼.

다음 라운드 작업 후보:
- `exec_path_suspicious` 신호의 임계 강화 (windows 의 정상 앱 다수가 %APPDATA% 거주 — sustained + cmdline 조건 추가)
- `persistent_ext` 의 정의에 "외부 endpoint 이 운영 시간 동안 변경 없음" 조건 추가 (게임 서버 / streaming CDN 은 endpoint 자주 변경되므로 자연 회피)
- 또는 backdoor signature 자체에 mining 의 fast-path 처럼 process_name + port + path 등 더 구체적 marker 요구

---

## 9. 누적 효과 분해

각 PR 의 이론적 기여 vs 실측:

| 변경 | 이론 효과 | 실측 (4,853 → 54) |
|---|---|---|
| P0-1 LOW/OBSERVE skip | -3,330 (68.6%) | 부분 기여 — 새 측정에 LOW/OBSERVE 자체 없음 |
| P0-2 verdict → severity | -559 (불일치) | 100% 차단 — 0건 |
| P0-3 gating + evidence_meta | MEDIUM 의 단일신호 진입 차단 | 54건 모두 gating 통과 (4+ signals 충족) |
| HW threshold | LOCAL_HW_CPU 308건 → 0 | local_evidence 0건 확인 |
| P1-3 cooldown | 5초 간격 → 60초 압축 | min_gap 60.002s 검증 |
| P1-1 local_evidence | LOCAL_* 분리 | active_signal_count 에서 LOCAL_* 제외됨 |

→ **5/6 PR 이 실측에서 명확히 작동 중**. P0-1 만 새 측정에 검증 데이터 부족 (그 자체로 발생 자체가 없어서).

---

## 10. 한계 / 다음 단계

### 본 측정의 한계
- 단일 PC, 단일 사용자 패턴 (4h38m)
- mining 동시 시뮬레이션 안 함 — 본 측정으로는 "P0/P1 가 진짜 mining 을 놓치는지" 미검증
- backdoor signature 가 dev 환경과 겹치는 문제 — P0/P1 으로 해결 안 됨

### 검증 권장
- `tools/anomaly_trigger.py` 한 번 실행하고 anomaly_history 에 HIGH_RISK 등록되는지 확인 (예상: 정상 동작 — fast-path 의 mining_known)
- 학생 PC 다수 며칠 분량 데이터로 long-run FP rate 측정

### 다음 라운드 후보
1. `SUSPICIOUS_BACKDOOR` signature 강화 (위 §8) — dev 환경 자연스러운 패턴 회피
2. **Grafana 카테고리 + evidence_meta + local_evidence 패널** — score/verdict 분리 대응 (이전 권고)
3. P0-1 의 2단계 (ML 응답에 `should_persist=false` 명시) — 운영 한 학기 안정 후 도입
4. retrieval_evidence 의 borderline 효과 정량 측정 (R2 합성 결과 → 실데이터)

---

## 부록 — 본 분석 재현 쿼리

```sql
-- §2 전체 분포
SELECT COUNT(*) FROM pc_monitor.metrics_history
WHERE pc_id='0c7a15737f66' AND collected_at > '2026-05-24 15:12:00+09';
SELECT COUNT(*) FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66' AND detected_at > '2026-05-24 15:12:00+09';

-- §3 severity × verdict
SELECT severity, anomaly_type, COUNT(*)
FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66' AND detected_at > '2026-05-24 15:12:00+09'
GROUP BY severity, anomaly_type ORDER BY COUNT(*) DESC;

-- §4 evidence_meta gating
SELECT scores->'evidence_meta'->>'promotion_gated' AS gated,
       scores->'evidence_meta'->>'fast_path_match' AS fast_path,
       scores->'evidence_meta'->>'promotion_reason' AS reason,
       COUNT(*)
FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66' AND detected_at > '2026-05-24 15:12:00+09'
GROUP BY gated, fast_path, reason;

-- §6 cooldown gap
WITH gaps AS (
  SELECT anomaly_type, detected_at,
         detected_at - LAG(detected_at) OVER (
             PARTITION BY anomaly_type ORDER BY detected_at) AS gap
  FROM pc_monitor.anomaly_history
  WHERE pc_id='0c7a15737f66' AND detected_at > '2026-05-24 15:12:00+09'
)
SELECT anomaly_type, MIN(gap) AS min_gap, AVG(gap)::interval AS avg_gap
FROM gaps WHERE gap IS NOT NULL GROUP BY anomaly_type;

-- §5 alert types
SELECT alert->>'type' AS alert_type, COUNT(*)
FROM pc_monitor.anomaly_history,
     jsonb_array_elements(alerts) AS alert
WHERE pc_id='0c7a15737f66' AND detected_at > '2026-05-24 15:12:00+09'
GROUP BY alert_type ORDER BY COUNT(*) DESC;
```

---

**결론**: P0 + HW threshold + P1 묶음이 실측 환경에서 의도대로 작동. anomaly_history 생성률 65.9% → 1.6% (41× 감소), severity-verdict 불일치 0, cooldown 정확히 60초 압축. 남은 FP 잠재 후보는 SUSPICIOUS_BACKDOOR 의 signature 자체가 dev 환경과 겹치는 부분으로, 별도 라운드에서 처리.
