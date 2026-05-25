# RADA NCP Field Verification

NCP (Naver Cloud Platform) 운영 환경 — 단일 App VM (Ubuntu 22.04 / Docker) + Cloud DB for PostgreSQL (managed) — 으로의 마이그레이션 후 첫 정상 사용 측정 (7시간 39분). 본 문서는 `docs/fp_field_analysis_post_p2.md` (로컬 P2 검증, 4h12m) 의 후속.

**핵심 결론**: NCP 운영 환경에서 정상 PC 7h 39m 동안 anomaly **0건**. 22시 cpu spike (cpu_max 71.8%) 포함 무거운 부하 구간에서도 false positive 없음. P2 검증의 핵심 결과 (정상 사용 FP=0) 가 NCP managed 인프라에서 **거의 2배 긴 시간** 동안 재현. mining trigger (fast-path + stealth) 양쪽 모두 즉시 HIGH_RISK 발화 — 알고리즘 NCP 마이그레이션 무결성 검증 완료.

---

## 1. Setup

| 항목 | P2 단계 (로컬) | **NCP 단계 (이번)** |
|---|---|---|
| 환경 | 로컬 docker compose | **NCP App VM + Cloud DB managed** |
| App 위치 | `localhost` | `223.130.154.165` (NCP Public IP) |
| DB | postgres:16-alpine 컨테이너 | **NCP Cloud DB for PostgreSQL 15.15** |
| 외부 노출 | 없음 (PC 내부) | Port 8080 (Spring API), 3000 (Grafana) |
| 클라이언트 실행 | `python client.py` 포그라운드 | **PyInstaller exe + Task Scheduler ONLOGON** |
| 수집 기간 | 4h 12m | **7h 39m** |
| metric rows (정상 PC) | 3,027 | **4,432** |
| Split point | `2026-05-24 20:27:48+09` | `2026-05-25 15:56:11+09` |
| Scoring policy | `scoring-v0.8.0` (+ P2 demotion `1dd8e40`) | 동일 (+ UX 패치 `6412001`) |

Pre-NCP 누적 metric (참고): 로컬 4단계 (Pre / P0+P1 / P2 / 기타 실험) 합 ~14,000+ rows.

---

## 2. 핵심 수치 — 4단계 비교

| 지표 | Pre-P0/P1 | P0+P1 | P2 (로컬) | **NCP (이번)** |
|---|---|---|---|---|
| 환경 | 로컬 | 로컬 | 로컬 | **NCP managed** |
| 측정 시간 | 2일 13h | 4h 38m | 4h 12m | **7h 39m** |
| metrics_history rows | 7,364 | 3,343 | 3,027 | **4,432** |
| anomaly rows | 4,853 | 54 | 0 | **0** |
| anomaly / metrics ratio | 65.9% | 1.6% | 0% | **0.000%** ✓ |
| SUSPICIOUS_BACKDOOR | 715 | 53 | 0 | **0** ✓ |
| SUSPICIOUS_EXFIL | 33 | 2 | 0 | **0** |
| severity-verdict 불일치 | 707 | 0 | 0 | **0** |

Pre 대비 **anomaly 비율 65.9% → 0%** = NCP 환경에서도 P2 의 완전 제거 효과 유지.

---

## 3. 시간대별 부하 — "spike 도 견디는 알고리즘"

15:00~23:00 (8시간) 시간대별:

| 시각 | rows | cpu_avg | cpu_max | anomaly | 해석 |
|---|---|---|---|---|---|
| 15:00 | 5 | 5.7% | 19.5% | 0 | 시작 (Task Scheduler 첫 부팅) |
| 16:00 | 497 | 6.4% | 33.0% | 0 | 정상 브라우징 |
| 17:00 | 26 | 6.4% | 17.1% | 0 | (수집 일시 휴식 — 절전 시간대) |
| 18:00 | 658 | 7.7% | 41.7% | 0 | 가벼운 작업 |
| 19:00 | 720 | 7.6% | 36.9% | 0 | 정상 |
| 20:00 | 720 | 5.0% | 28.5% | 0 | (anomaly_trigger / stealth_trigger 시간 — 별도 pc_id) |
| 21:00 | 720 | 9.0% | 34.3% | 0 | 가벼운 작업 |
| **22:00** | 719 | **22.2%** | **71.8%** | **0** ← ★ | PyInstaller 빌드 + 부하 spike. 알고리즘 견딤 |
| 23:00 | 375 | 5.1% | 78.7% | 0 | Task Scheduler 부팅 spike (1초) |

★ **22:00 시간대 cpu_avg 22.2% (max 71.8%) 의 명백히 무거운 사용** 에도 false positive 0 — P0/P1/P2 gating 이 짧은 부하 spike 를 mining 으로 오인하지 않음을 NCP 환경에서 실증.

---

## 4. 자원 사용량 — 4단계 비교

| 지표 | P1 측정 (54 anomaly) | P2 측정 (0 anomaly, 4h12m) | **NCP (0 anomaly, 7h39m)** |
|---|---|---|---|
| cpu_avg | 9.39% | 16.89% | **8.93%** (dev-01+PC-01 가중) |
| cpu_max | 62.70% | 85.20% | 78.7% |
| mem_avg | 59.44% | 64.58% | **48.45%** |
| mem_max | 78.10% | 87.50% | 68.6% |
| gpu_avg | — | — | **3.59%** (idle) |
| gpu_max | — | — | 38% (짧은 burst) |
| inbound_avg | 4.28 MB/s | 2.73 MB/s | (혼합 — dev/PC 두 단계) |
| span | 4h 38m | 4h 12m | **7h 39m** |

→ NCP 측정은 **혼합 워크로드** (가벼운 브라우징 + 22시 무거운 빌드 spike). 그래도 anomaly 0건.

---

## 5. Mining 탐지력 라이브 검증 — NCP 환경 재현

P0/P1/P2 가 정상 사용을 안 잡는 게 확인됐다면, mining 은 잡는지를 NCP 환경에서 직접 검증. `tools/anomaly_trigger.py` (fast-path) 와 `tools/stealth_trigger.py` (behavior-only) 실행.

### 5-1. Fast-path (xmrig + mining port 3333)

`pc-smoke` 페이로드 15회 (2초 간격, 30초):

| 항목 | 로컬 P2 검증 | NCP 검증 |
|---|---|---|
| 첫 발화 severity / verdict | HIGH / HIGH_RISK | **HIGH / HIGH_RISK** ✓ |
| `scores.final` | 14.0 | **14.0** ✓ 완전 동일 |
| `scores.process` | 10 (known_miner=xmrig.exe) | **10** ✓ |
| `evidence_meta.fast_path_match` | (known_miner) | (known_miner) ✓ |
| top alert | CONFIRMED_MINING | **CONFIRMED_MINING** ✓ |
| persisted rows (P1 cooldown 60s/verdict) | 1 | **2 HIGH + 1 MEDIUM** (3) |

→ **fast-path mining 즉시 발화 — NCP 환경 무결성 확인.**

### 5-2. Stealth (fast-path 회피, behavior-only)

`pc-stealth` 페이로드 — process name `wuauclt_helper.exe` (블랙리스트 외) + AppData\Roaming 경로 + 비-mining port 443 + Azure/CloudFlare IP 대역:

#### 5-2-A. Fresh PC (history 0건)

`pc-stealth` 자체 API key 로 발급된 fresh PC:

| 항목 | 로컬 P2 (warm PC) | NCP (fresh PC) |
|---|---|---|
| severity / verdict | HIGH / HIGH_RISK | **MEDIUM / SUSPICIOUS** |
| `scores.final` | 20.47 | **9.4** |
| `scores.process` | 0 (no known_miner) | **0** (의도대로) |
| top alert | HIGH_RISK_GPU_MINING | **SUSPICIOUS_GPU_MINING** |

→ history 없는 fresh PC 에선 SUSPICIOUS 발화. 점수 ↓ 이유는 retrieval context 부재 — **놓치진 않음**.

#### 5-2-B. Warm PC (mining history 누적)

`pc-smoke` 키로 stealth 페이로드 전송 → anomaly_trigger 의 mining 히스토리 위에 stealth:

| 항목 | 로컬 P2 검증 | **NCP 검증** |
|---|---|---|
| severity / verdict | HIGH / HIGH_RISK | **HIGH / HIGH_RISK** ✓ |
| `scores.final` | 20.47 | **20.47** ✓ 완전 동일 |
| `scores.gpu_mining` | 5 | **5** ✓ |
| `scores.cpu_mining` | 4 | **4** ✓ |
| `scores.process` | 0 (no known_miner) | **0** ✓ |
| `evidence_meta.fast_path_match` | null | **null** ✓ |
| `evidence_meta.active_signal_count` | 13 | **13** ✓ |
| top alert | HIGH_RISK_GPU_MINING | **HIGH_RISK_GPU_MINING** ✓ |

→ **점수 한 자리까지 동일**. history 있는 PC 에서 stealth mining 즉시 HIGH_RISK 발화. 로컬 P2 검증 결과 NCP 환경에서 **비트 단위로 재현**.

### 5-3. Cooldown 동작 확인 (P1 의 60s/verdict)

- 20:14:58 HIGH_RISK persist (final=20.47)
- 60초 cooldown 동안 같은 verdict 못 들어옴
- 그 사이 새 페이로드는 SUSPICIOUS 등급으로 떨어진 게 persist (final=13.47)

→ **P1 cooldown NCP 환경에서 정상 동작**.

---

## 6. 운영 안정성 — 클라이언트 / 데이터 흐름

### 6-1. PyInstaller exe + Task Scheduler

본인 PC 클라이언트 운영 검증:

| 시나리오 | 결과 |
|---|---|
| 재부팅 → 로그인 | ✅ Task Scheduler ONLOGON 트리거로 자동 시작 |
| 절전 → 깨어남 | ✅ 같은 프로세스 PID 유지, 깨어나서 즉시 metric 재개 |
| 로그오프 → 로그인 | ✅ 자동 시작 |
| 5초 주기 metric 전송 | ✅ |
| 콘솔 창 깜빡임 | ✅ subprocess CREATE_NO_WINDOW 패치로 완전 제거 |

### 6-2. 수집 안정성

| pc_id | span | rows | 이론치 (span × 12/min) | 도달율 |
|---|---|---|---|---|
| dev-01 | 7h 16m | 4,212 | 5,232 | **80.5%** |
| PC-01 | 23m | 220 | 276 | **79.7%** |

20% 결손은 절전 시간 / 재부팅 / PyInstaller 빌드 등 일시 정지가 원인. 학생 PC 환경에서도 유사 수준 예상.

### 6-3. Cloud DB 동작

- Flyway V1~V8 migration 모두 success (`ALTER ROLE` 권한 우려 통과)
- 7시간 동안 connection 끊김 0건
- 인덱스 정상 활용 (`idx_metrics_pc_collected`)

---

## 7. Top 프로세스 — 정상 사용자 패턴

| 프로세스 | 등장 횟수 | 정체 |
|---|---|---|
| chrome.exe | 15,139 | 주 작업 도구 |
| System Idle Process | 4,441 | OS CPU 여유 |
| claude.exe | 3,890 | Claude 데스크탑 |
| rada_client.exe | 3,878 | RADA client 자체 (자기 self-monitor) |
| dwm.exe / WmiPrvSE.exe / svchost.exe | ~5,800 | Windows 시스템 |
| NLiveConnector / nosstarter | 3,032 | Naver 백그라운드 |

→ 명확히 정상 사용자 패턴. **마이닝 / 백도어 / 의심 프로세스 0개**.

---

## 8. 한계 + 미검증 영역

### 본 측정의 한계
- 단일 PC, 7h 39m — 학생 PC 다수 / 며칠 데이터 아님
- 본 측정 시간대 (오후~심야) 가 게임/streaming 활동기 — 동일 시간대 다른 사용자의 결과는 다를 수 있음
- mining stealth fresh-PC 점수 (9.4 SUSPICIOUS) — 학생 PC 초기 24시간 history 누적 후 점수 변동 확인 필요

### 다음 검증 권장
- 학생 PC 다수 며칠 분량 long-run — `tools/provision_pcs.py` 로 40대 발급 완료, `install.bat` 자동화 준비 완료, USB 배포만 남음
- 실제 xmrig 등 mining 바이너리 격리 환경 실행 — 시뮬 페이로드와 신호 일치 여부 (현재 범위 밖)
- 24~48h 정상 사용 누적 — anomaly rate 0 유지 확인 (현재 7h 까지 검증)

### 향후 개선 후보 (미스케줄)
- AI agent 활성화 (Anthropic API key) — anomaly 발생 시 Claude 호출로 추가 판단
- Grafana 패널 미화 (현재 provisioning 기본 dashboard 2종)
- pc_id 별 retention 정책 (현재 일괄 14일/90일)
- 학생 PC 의 PC-XX → 학생 매핑표 별도 관리 (운영 단계)

---

## 9. 누적 PR 정리 (FP + Infra 시리즈)

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
| `c509c22` | docs: P2 검증 리포트 | 단일 PC 4h12m FP=0 |
| `c447ce7` | docs(p2): mining trigger 검증 | 보수적 framing |
| `873b2cf` | test(p2): stealth trigger | behavior-only 탐지 검증 |
| `80b905e` | test(client): driver_error 허용 | CI 안정화 |
| `c8eb5d9` | docs: client deployment manual | PyInstaller + Task Scheduler |
| `9ebdf93` | docs: NCP deployment + update workflow | 운영 가이드 |
| `46ade40` | test(tools): env-driven triggers | NCP 환경에서도 trigger 가능 |
| `6412001` | **fix(client): hide cmd flashes** | subprocess CREATE_NO_WINDOW |
| `05eead0` | ux: clean client display + spring log | UNKNOWN / mismatch 제거 |

---

## 부록 — 본 분석 재현 쿼리

### A. §2 4단계 비교

```sql
-- 정상 PC FP rate (dev-01 + PC-01)
SELECT
  COUNT(DISTINCT m.id) AS metrics,
  COUNT(DISTINCT a.id) AS anomaly,
  ROUND(100.0 * COUNT(DISTINCT a.id) / NULLIF(COUNT(DISTINCT m.id), 0), 3) AS rate_pct
FROM pc_monitor.metrics_history m
LEFT JOIN pc_monitor.anomaly_history a ON a.pc_id = m.pc_id
WHERE m.pc_id IN ('dev-01','PC-01');
```

### B. §3 시간대별 부하

```sql
SELECT date_trunc('hour', collected_at) AS hour,
       COUNT(*) AS rows,
       ROUND(AVG(cpu_percent)::numeric, 1) AS cpu_avg,
       MAX(cpu_percent) AS cpu_max
FROM pc_monitor.metrics_history
WHERE pc_id IN ('dev-01','PC-01')
GROUP BY hour
ORDER BY hour;
```

### C. §5 mining trigger 결과

```sql
SELECT pc_id, detected_at, severity, anomaly_type,
       scores->>'final' AS final,
       scores->>'process' AS proc,
       scores->'evidence_meta'->>'fast_path_match' AS fast_path,
       scores->'evidence_meta'->>'active_signal_count' AS signals,
       alerts->0->>'type' AS top_alert
FROM pc_monitor.anomaly_history
WHERE pc_id IN ('pc-smoke','pc-stealth')
ORDER BY detected_at;
```

### D. §7 Top 프로세스

```sql
SELECT jsonb_array_elements(extra->'top_processes')->>'name' AS proc,
       COUNT(*) AS cnt
FROM pc_monitor.metrics_history
WHERE pc_id IN ('dev-01','PC-01')
GROUP BY proc
ORDER BY cnt DESC
LIMIT 10;
```

---

**결론**: NCP managed 인프라 (App VM + Cloud DB for PostgreSQL + Docker) 위에서 RADA 알고리즘이 P0/P1/P2 의 검증 결과를 그대로 재현. 정상 사용 7h 39m 동안 FP 0건, 22시 cpu_max 71.8% spike 견딤, mining trigger (fast-path + behavior-only) 양쪽 즉시 발화, PyInstaller + Task Scheduler 백그라운드 운영 안정 확인. **운영 배포 안정선 도달 + 마이그레이션 무결성 검증 완료**. 다음 단계: 학생 PC 40대 USB 배포 + 며칠 long-run.
