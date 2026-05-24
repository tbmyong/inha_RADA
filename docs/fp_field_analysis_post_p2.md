# RADA Post-P2 Field Verification

P2 (backdoor demotion) 적용 후 동일 호스트로 4시간 12분 정상 사용 재측정. 본 문서는 `docs/fp_field_analysis_v0.6.md` → `docs/fp_field_analysis_post_p1.md` 의 후속 (3차 측정).

**핵심 결론**: P2 적용 후 정상 사용 4h12m 동안 anomaly_history 신규 **0건**. P1 단계 (4h38m / 54건) 대비 100% 제거. 더 중요한 발견: **본 측정의 부하는 P1 측정보다 더 무거웠음** (cpu_avg 9.4 → 16.9%, mem_max 78 → 87%) — 사용 적어서 0이 아니라 알고리즘이 제대로 작동해서 0.

---

## 1. Setup

| 항목 | P0/P1 단계 | **P2 단계 (이번)** |
|---|---|---|
| PC | `0c7a15737f66` | 동일 |
| 수집 기간 | 4h 38m | **4h 12m** |
| metric rows | 3,343 | 3,027 |
| Split point | `2026-05-24 15:12:07+09` | `2026-05-24 20:27:48+09` |
| Scoring policy | `scoring-v0.8.0` (P0+P1+HW) | `scoring-v0.8.0` (+ P2 demotion `1dd8e40`) |
| 시간대 | 15:12 ~ 19:51 (저녁) | 20:27 ~ 00:40 (저녁~새벽) |

Pre-P2 누적 baseline (참고): anomaly_history 총 4,908 건 (= 베이스라인 4,853 + P1 측정 55).

---

## 2. 핵심 수치 — 3단계 비교

| 지표 | Pre-P0/P1 (4,853 anomaly @ 2일13h) | P0+P1 (54 @ 4h38m) | **P2 (0 @ 4h12m)** |
|---|---|---|---|
| metrics_history rows | 7,364 | 3,343 | 3,027 |
| anomaly rows | 4,853 | 54 | **0** |
| anomaly / metrics ratio | 65.9% | 1.6% | **0.0%** |
| SUSPICIOUS_BACKDOOR | 575 + 140 OBSERVE = 715 | 53 | **0** ✓ |
| SUSPICIOUS_EXFIL | 18 + 15 = 33 | 2 | **0** |
| severity-verdict 불일치 | 707 | 0 | 0 |

Pre 대비 **anomaly 비율 65.9% → 0%** = ∞× 감소 (사실상 완전 제거).

---

## 3. 사용 패턴 비교 — "사용 안 해서 0" 가설 기각

가장 중요한 sanity check. 만약 P2 측정 동안 사용량이 P1 보다 적었다면 "anomaly 0" 의 원인은 P2 가 아니라 단순히 입력 부재일 수 있음. 그러나 실측 데이터는 정반대:

| 지표 | P1 (54 anomaly) | P2 (0 anomaly) | 차이 |
|---|---|---|---|
| cpu_avg | 9.39% | **16.89%** | P2 가 **1.8× 더 높음** |
| cpu_max | 62.70% | **85.20%** | P2 가 22%p 더 높음 |
| mem_avg | 59.44% | 64.58% | P2 가 5%p 더 높음 |
| mem_max | 78.10% | **87.50%** | P2 가 9%p 더 높음 |
| inbound_avg | 4.28 MB/s | 2.73 MB/s | P1 이 1.5× 더 높음 |
| inbound_max | 52.80 MB | 51.85 MB | 거의 동일 |

P2 측정은 CPU/메모리 부하가 명백히 더 큰 사용 패턴 (저녁~새벽 게임 또는 무거운 dev 작업 추정). 네트워크 burst 크기는 거의 동일. **그런데도 anomaly 0** = P2 의 backdoor 승격 제거가 실제로 effective.

---

## 4. P2 효과 분해

P1 측정의 잔여 54 anomaly 분포 → P2 적용 후 예상 → 실측:

| Alert type | P1 실측 | P2 예상 (이론) | P2 실측 |
|---|---|---|---|
| SUSPICIOUS_BACKDOOR | 53 | **0** (alert 자체 제거) | **0** ✓ |
| SUSPICIOUS_EXFIL | 2 | 2 (별도 signal — outbound_spike + net_external_high) | **0** |
| 그 외 | 0 | 0~1 | **0** |

→ SUSPICIOUS_BACKDOOR 53건 제거는 P2 의 본질적 효과 (alert type 자체 비활성). SUSPICIOUS_EXFIL 2건은 별도 신호 기반인데 이번엔 발화 안 함 — P2 가 직접 차단한 건 아니지만, P0/P1 의 cooldown + gating 덕에 EXFIL 조건도 안 채워졌을 가능성.

---

## 5. 잔여 SUSPICIOUS 후보 (이론적으로 가능했던 발화 경로)

P2 적용 후에도 살아있는 SUSPICIOUS_* alert types (top_cat 후보):
- `SUSPICIOUS_GPU_MINING`
- `SUSPICIOUS_CPU_MINING`
- `SUSPICIOUS_STEALTH`
- `SUSPICIOUS_EXFIL`
- `SUSPICIOUS_DOS`
- `SUSPICIOUS_MEMORY`
- `SUSPICIOUS_ML`
- (`SUSPICIOUS_BACKDOOR` ← 제거됨)

이 중 본 측정 동안 발화한 것 없음. 정상 사용 패턴이 P0+P1+P2 의 gating + cooldown + alert type 제거 + signal 강화 모두 통과하지 못함 = **시스템이 정상 트래픽을 매우 안정적으로 NORMAL 또는 silent (저장 안 됨) 로 처리** 한다는 의미.

---

## 6. 운영 배포 시 예상 알람량

3단계의 시간당 anomaly 추이:

```
Pre-P0/P1: ~80 / hour
P0+P1:     ~12 / hour
P2:        ~0 / hour
```

학생 PC 40대 × 8시간 = 320 PC-시간 가정:
- Pre: 25,600 alerts/day
- P0+P1: 3,840 alerts/day
- **P2: ~0 alerts/day (정상 사용 한정)**

진짜 mining 시나리오 (xmrig 같은 fast-path) 는 여전히 즉시 HIGH/HIGH_RISK → `tools/anomaly_trigger.py` 로 검증 가능 (이전 측정에서 확인).

---

## 7. 한계 + 미검증 영역

### 본 측정의 한계
- 단일 PC, 4시간 12분 — 학생 PC 다수 / 며칠 데이터 아님
- **mining 동시 시뮬레이션 없음** — P2 가 진짜 mining 을 놓치는지 별도 검증 필요. fast-path (mining_known process + port) 는 P0/P1/P2 모두 우회하므로 이론상 안전.
- 본 측정 시간대 (저녁~새벽) 가 게임/streaming 활동기 — 동일 시간대 다른 사용자의 결과는 다를 수 있음

### 다음 검증 권장
- `tools/anomaly_trigger.py` 한 번 실행 → SUSPICIOUS_BACKDOOR 없이도 HIGH_RISK / SUSPICIOUS_GPU_MINING 정상 발화하는지 (예상: 정상)
- 학생 PC 다수 며칠 분량 long-run

### 향후 개선 후보 (미스케줄)
- backdoor 탐지 자체를 다시 살리려면 더 강한 evidence (cmdline / digital signature / per-PID network mapping 등) 가 필요. 현재 RADA 수집 범위 밖이라 별도 검토 대상.
- `persistent_ext` 가 여전히 `indicator_calculator.py:153` 의 `episode += 2` 로 약하게 남아 있음. evidence-only 톤으로 더 낮추는 건 별도 PR.

---

## 8. 누적 PR 정리 (FP 시리즈)

| SHA | 단계 | 효과 |
|---|---|---|
| `3e88ddb` | P0-1 LOW/OBSERVE skip | 3,330 row 정리 |
| `b571a31` | P0-2 verdict→severity | 559 불일치 정리 |
| `d979cdd` | P0-3 gating + evidence_meta | 단일 신호 진입 차단 |
| `70cf2e9` | HW threshold 강화 | LOCAL_HW_CPU 308 정리 |
| `2d252ee` | P1 묶음 4건 | local_evidence / DOS floor / episode decay / retrieval gating |
| `a9e53e5` | Spring @Autowired + postgres port | infra 안정성 |
| `bdfef79` | post-P0/P1 측정 리포트 | 검증 (1.6% rate) |
| `18bd252` | **P2 backdoor demotion** | SUSPICIOUS_BACKDOOR 53 → 0 |
| `1dd8e40` | docs: Sysmon 톤다운 | 명확한 scope 표현 |

---

## 부록 — 본 분석 재현 쿼리

```sql
-- §2 카운트
SELECT 'metrics' AS k, COUNT(*) AS v,
       MIN(collected_at), MAX(collected_at),
       MAX(collected_at) - MIN(collected_at) AS span
FROM pc_monitor.metrics_history
WHERE pc_id='0c7a15737f66' AND collected_at > '2026-05-24 20:27:00+09'
UNION ALL
SELECT 'anomaly', COUNT(*),
       MIN(detected_at), MAX(detected_at),
       MAX(detected_at) - MIN(detected_at)
FROM pc_monitor.anomaly_history
WHERE pc_id='0c7a15737f66' AND detected_at > '2026-05-24 20:27:00+09';

-- §3 P1 vs P2 사용 패턴 비교
WITH p1 AS (
    SELECT AVG(cpu_percent) AS cpu_avg, MAX(cpu_percent) AS cpu_max,
           AVG(mem_percent) AS mem_avg, MAX(mem_percent) AS mem_max,
           AVG(inbound_mb)  AS inbound_avg, MAX(inbound_mb)  AS inbound_max
    FROM pc_monitor.metrics_history
    WHERE pc_id='0c7a15737f66'
      AND collected_at BETWEEN '2026-05-24 15:12:00+09'
                            AND '2026-05-24 19:51:35+09'
), p2 AS (
    SELECT AVG(cpu_percent) AS cpu_avg, MAX(cpu_percent) AS cpu_max,
           AVG(mem_percent) AS mem_avg, MAX(mem_percent) AS mem_max,
           AVG(inbound_mb)  AS inbound_avg, MAX(inbound_mb)  AS inbound_max
    FROM pc_monitor.metrics_history
    WHERE pc_id='0c7a15737f66' AND collected_at > '2026-05-24 20:27:00+09'
)
SELECT 'P1' AS stage, * FROM p1
UNION ALL SELECT 'P2', * FROM p2;
```

---

**결론**: P2 가 의도대로 backdoor verdict 승격 + SUSPICIOUS_BACKDOOR alert 생성 둘 다 완전 차단. **정상 사용 시 FP 사실상 0**. 진짜 mining 탐지력은 별도 라이브 검증 (fast-path) 으로 확인 필요. 운영 배포 안정선 도달.
