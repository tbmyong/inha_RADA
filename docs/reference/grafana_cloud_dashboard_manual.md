# RADA Grafana Dashboard & NCP 운영 매뉴얼

이 문서는 팀원이 GitHub에서 공동작업을 시작할 때 공유하기 위한 대시보드/클라우드 설계
메모이다. 범위는 최종평가용 Grafana 시각화, React panel plugin 우선순위, NCP 배포
성능 전략, refresh 주기, 탄소중립 패널 기획까지 포함한다.

## 1. 최종평가 기준 중요도

RADA는 탐지 시스템이므로 백엔드/ML 완성도가 최우선이다. 다만 최종평가에 심미성이
포함되므로 대시보드의 첫인상도 거의 같은 수준으로 중요하다.

| 항목 | 중요도 | 현재 판단 |
|---|---:|---|
| 백엔드/ML 안정성 | 35% | 매우 중요. 5초 수집, 저장, ML 분석, scoring, retrieval evidence, AI 설명 흐름이 실제로 이어져야 한다. |
| 대시보드/시각화 심미성 | 30% | 매우 중요. 평가자가 완성도를 체감하는 첫 화면이다. |
| 논문 반영 설명력 | 15% | 중요. Retrieval-Augmented Time-Series Evidence Layer를 정확히 설명해야 한다. |
| NCP 배포/운영성 | 10% | 중요. systemd, DB, Grafana가 실제 VM에서 안정적으로 떠야 한다. |
| 테스트/문서/README | 10% | 중요. 팀원이 재현할 수 있어야 한다. |

현재 완성도 평가는 대략 백엔드/ML은 80%대, 대시보드 심미성은 아직 50% 미만으로 본다.
따라서 다음 점수 상승 효율이 가장 큰 작업은 React 기반 대시보드 패널이다.

## 2. Grafana React Plugin 판단

Grafana panel plugin은 React 컴포넌트로 만들 수 있으며, `create-plugin`으로 스캐폴딩하는
공식 방식이 있다. 구조적으로 Grafana 안에서 동작하는 작은 React 앱으로 보면 된다.

기본 Grafana 패널과 Canvas도 좌석 배치나 간단한 오버레이에는 쓸 수 있다. 하지만 최종평가
심미성을 고려하면 다음 기능은 React panel plugin 쪽이 더 적합하다.

- 자동차 계기판 같은 startup animation
- 위험 PC pulse/glow
- 좌석별 hover tooltip
- 클릭 시 PC 상세 dashboard 이동
- 탄소중립 나무 시각화
- 추후 공격 timeline, process graph, network flow animation

주의할 점은 plugin 서명이다. 자체 NCP Grafana에서 개발/시연할 때는 unsigned plugin을
허용할 수 있지만, 운영 품질을 말하려면 signing 또는 Canvas fallback 계획을 함께 설명해야 한다.

## 3. 추천 패널 우선순위

최종평가용 1차 목표는 고급 기능을 많이 넣는 것보다 첫 화면을 제품처럼 보이게 만드는 것이다.

### 1순위: RADA Room Map Panel

실습실 PC 40대를 좌석 배치도로 보여주는 핵심 패널이다.

기능:

- 실습실 평면도 또는 좌석 grid
- 좌석별 PC 아이콘
- verdict/risk score별 색상
- 위험 PC 빨간 glow/pulse
- hover 시 PC 정보 표시
- 클릭 시 PC 상세 대시보드로 이동

예상 데이터:

```json
{
  "pc_id": "PC-12",
  "x": 420,
  "y": 180,
  "risk_score": 87,
  "verdict": "HIGH_RISK",
  "last_seen": "2026-05-19T10:22:00"
}
```

색상 규칙:

| 상태 | 표현 |
|---|---|
| NORMAL / SAFE | 은은한 초록 |
| OBSERVE | 노랑 |
| SUSPICIOUS | 주황 |
| HIGH_RISK / CRITICAL | 빨간 pulse + halo |
| OFFLINE | 회색 / 투명 |

### 2순위: RADA Risk Speedometer Panel

선택된 PC 또는 실습실 전체 위험도를 계기판 형태로 보여준다.

기능:

- final score gauge
- verdict badge
- `score_breakdown` 요약
- retrieval score 강조
- 최근 HIGH_RISK 발생 시 startup animation

예상 데이터:

```json
{
  "pc_id": "PC-12",
  "final_score": 18,
  "verdict": "HIGH_RISK",
  "score_breakdown": {
    "resource": 3,
    "network": 4,
    "process": 2,
    "episode": 2,
    "correlation": 3,
    "ml": 2,
    "retrieval": 3,
    "context_discount": -1,
    "final": 18
  }
}
```

### 3순위: RADA Carbon Tree Panel

Attack Timeline 대신 탄소중립과 연결한 심미성 패널이다. RADA가 수집하는 CPU/GPU/전력
관련 metric을 사용해 실습실 에너지 사용과 탄소 배출을 추정한다.

중요: 실제 전력계가 아니므로 반드시 `estimated` 표현을 사용한다.

컨셉:

- PC 40대를 나무의 잎 40개에 매핑
- 효율적이면 나무가 초록색으로 풍성해짐
- 유휴 낭비, 고부하, 위험 PC가 늘면 잎이 노랑/주황/빨강으로 변함
- 위험 PC는 빨간 pulse leaf
- 절감 상태가 좋아지면 새 잎이 돋는 animation

예상 수치:

| 지표 | 의미 |
|---|---|
| `carbon_health` | 0~100 탄소 건강도 |
| `estimated_power_w` | 현재 추정 전력 |
| `energy_kwh_today` | 오늘 추정 전력 사용량 |
| `co2_kg_today` | 오늘 추정 탄소 배출량 |
| `idle_waste_kwh` | 유휴 낭비 전력 |
| `high_load_pc_count` | 고부하 PC 수 |
| `saving_rate` | 추정 절감 가능 비율 |

MVP 계산식:

```text
estimated_power_w =
  base_pc_w
  + cpu_percent / 100 * cpu_tdp_w
  + gpu_percent / 100 * gpu_tdp_w
  + memory_adjustment_w
```

```text
energy_kwh = estimated_power_w * duration_hours / 1000
co2_kg = energy_kwh * grid_emission_factor
```

예상 데이터:

```json
{
  "carbon_health": 82,
  "estimated_power_w": 2840,
  "energy_kwh_today": 12.4,
  "co2_kg_today": 5.3,
  "idle_waste_kwh": 1.2,
  "saving_rate": 17,
  "leaves": [
    {
      "pc_id": "PC-01",
      "state": "NORMAL",
      "estimated_power_w": 62,
      "idle_waste": false
    },
    {
      "pc_id": "PC-12",
      "state": "HIGH_RISK",
      "estimated_power_w": 310,
      "idle_waste": false
    }
  ]
}
```

### 후순위: Attack Timeline / Process Chain / Network Flow

이 패널들은 시각적으로 좋지만 데이터 기반이 먼저 필요하다.

- Process Chain은 parent/child process, event id, command line, external connection이 필요하다.
- Attack Timeline은 시간순 event와 공격 단계 분류가 필요하다.
- Network Flow는 외부 IP, 목적지 분류, bytes/s, C2/mining/exfil hint가 필요하다.

현재 RADA 단계에서는 1차 최종평가 범위가 아니라 향후 확장으로 두는 것이 안전하다.

## 4. NCP 성능 판단

NCP에서 대시보드가 부드럽게 동작하는지는 animation 자체보다 쿼리 구조와 refresh 주기에
더 크게 좌우된다. CSS/SVG/Canvas animation은 대부분 사용자 브라우저가 렌더링한다.
NCP 서버는 Spring, FastAPI, PostgreSQL, Grafana backend, API 쿼리를 버티면 된다.

권장 스펙:

| 규모 | 에이전트 | 접속자 | 권장 스펙 |
|---|---:|---:|---|
| 발표/데모 | 5~20대 | 1~3명 | 2 vCPU / 8GB 가능, 안정성은 4 vCPU 권장 |
| 실습실 PoC | 30~80대 | 3~10명 | 4 vCPU / 16GB 권장 |
| Sysmon 포함 운영형 | 100대 이상 | 10명 이상 | 8 vCPU / 32GB 또는 VM 분리 |

RADA는 Spring + FastAPI ML + PostgreSQL + Grafana를 단일 VM에 올리는 구조이므로,
최종 발표 안정성을 위해서는 4 vCPU / 16GB / SSD 구성을 권장한다.

## 5. 분석 주기와 화면 주기 분리

가장 중요한 운영 전략은 ML 분석 주기와 Grafana 화면 refresh 주기를 분리하는 것이다.

```text
Agent 수집 주기        5초
ML 분석 주기           5초
위험도/판정 갱신        5초
Grafana 화면 refresh   30초~60초
Critical alert         별도 즉시 처리
```

Grafana가 30초마다 갱신된다고 해서 ML이 30초마다 분석하는 것이 아니다. 백엔드는 5초마다
계속 분석하고, Grafana는 이미 계산된 최신 결과를 늦게 보는 구조다.

장점:

- Grafana 쿼리 부하가 크게 줄어든다.
- React panel re-render가 줄어 animation이 더 부드러워진다.
- 단일 NCP VM에서도 안정성이 올라간다.

단점:

- 화면 반영은 최대 refresh 주기만큼 늦어질 수 있다.
- 30초 refresh면 평균 지연은 약 15초, 최대 지연은 약 30초다.
- 따라서 CRITICAL 알림은 Grafana refresh에 의존하지 않고 별도 즉시 알림으로 처리해야 한다.

추천 refresh:

| 화면 | 권장 refresh |
|---|---:|
| Room Map | 10~30초 |
| Risk Speedometer | 10~30초 |
| PC 상세 상태 | 10~30초 |
| Carbon Tree | 30초~1분 |
| Process Chain | 30초 |
| Attack Timeline | 30초 |
| 장기 CPU/GPU 그래프 | 30초~1분 |
| 통계/랭킹/일별 추이 | 1~5분 |

## 6. 데이터 조회 구조

Grafana custom panel이 raw metric을 직접 많이 조회하면 NCP 부하가 커진다. 패널별로
복잡한 SQL을 반복 실행하는 구조는 피한다.

비추천:

```text
Grafana Panel 1 -> raw metrics 조회
Grafana Panel 2 -> raw metrics 조회
Grafana Panel 3 -> process logs 조회
Grafana Panel 4 -> network logs 조회
Grafana Panel 5 -> 직접 계산
```

추천:

```text
Agent -> Spring/FastAPI -> 5초 분석
                       -> latest summary 생성
                       -> DB summary table 또는 cache 저장
Grafana custom panel -> 30초마다 summary만 조회
```

1차 구현은 DB schema 변경 없이 기존 `anomaly_history`, `metrics_history`, `pc_info`를 조합한
쿼리로 시작할 수 있다. 이후 성능이 부족하면 `latest_pc_status` summary table 또는 Redis cache를
검토한다.

예상 summary payload:

```json
{
  "pc_id": "PC-12",
  "risk_score": 87,
  "verdict": "HIGH_RISK",
  "cpu": 82,
  "gpu": 91,
  "memory": 68,
  "network_state": "suspicious",
  "last_detected_at": "2026-05-19T10:00:25",
  "top_reason": "retrieval_high_risk_peer_mismatch"
}
```

## 7. React Panel 구현 규칙

성능과 심미성을 같이 잡기 위한 구현 규칙이다.

- CSS `transform`, `opacity`, SVG animation 위주로 처리한다.
- 모든 PC를 매 프레임 re-render하지 않는다.
- 위험 상태 PC만 pulse animation을 적용한다.
- `React.memo`와 stable props를 사용한다.
- 데이터가 바뀐 PC만 업데이트한다.
- 좌석 40개 정도는 SVG/HTML DOM 모두 가능하다.
- process graph는 처음부터 수백 노드를 렌더링하지 않는다.
- network flow는 SVG path 또는 Canvas를 사용한다.
- 5초마다 전체 graph를 unmount/remount하지 않는다.

피해야 할 것:

- 모든 좌석이 계속 깜빡이는 UI
- 모든 네트워크 선이 무한 animation
- raw event를 panel 내부에서 무겁게 가공
- 패널 10개 이상을 모두 5초 refresh로 설정
- 실제 전력 측정이 아닌데 탄소 수치를 확정값처럼 표현

## 8. 팀 작업 분배 제안

공동작업 초기에는 다음처럼 나누면 충돌이 적다.

| 역할 | 담당 범위 | 산출물 |
|---|---|---|
| Dashboard UI | React panel plugin, Room Map, Risk Gauge, Carbon Tree | `grafana-plugins/` 또는 별도 plugin repo |
| Backend API | room-state/pc-summary/carbon-summary endpoint 또는 SQL view | Spring QueryController 또는 Grafana SQL |
| ML/Scoring | final score, verdict, retrieval evidence 안정화 | `ml_server/` |
| Infra/NCP | systemd, Grafana plugin 배포, unsigned plugin 설정, refresh 정책 | `infra/ncp/`, `infra/grafana/` |
| QA/Docs | smoke, README, 발표용 시나리오, 스크린샷 | `docs/`, root README |

처음부터 DB schema를 바꾸는 작업은 피한다. 필요하면 팀 합의 후 별도 migration으로 처리한다.

## 9. 1차 마일스톤

### M1: 발표용 시각화 MVP

목표:

- Room Map Panel
- Risk Speedometer Panel
- Carbon Tree Panel
- Grafana refresh 30초
- 클릭 시 PC detail dashboard 이동

완료 기준:

- HIGH_RISK PC가 빨간 pulse로 표시된다.
- PC hover 시 CPU/GPU/verdict/last_seen이 보인다.
- 선택 PC의 final score와 score breakdown이 gauge에 반영된다.
- Carbon Tree가 estimated CO2/energy 수치를 표시한다.
- 대시보드가 30초 refresh에서 끊김 없이 동작한다.

### M2: 운영형 개선

목표:

- summary API 또는 summary query 정리
- NCP 4 vCPU / 16GB 기준 부하 확인
- unsigned plugin 설정 또는 signing 계획 정리
- Critical alert 즉시 알림 경로 분리

완료 기준:

- Spring/FastAPI/Grafana systemd 기동 확인
- Grafana panel 3~5개 동시 표시에서 CPU/RAM 안정
- refresh 30초 기준 DB query 부하가 과하지 않음

## 10. 최종 발표 메시지

대시보드는 다음 메시지를 전달해야 한다.

```text
RADA는 5초 단위 PC 자원 데이터를 수집하고,
ML/룰/retrieval evidence로 이상 여부를 판단하며,
Grafana React dashboard에서 실습실 전체 위험 상태와 탄소중립 관점의 에너지 영향을
한눈에 보여준다.
```

표현 주의:

- `Deep Feature-Based 구현 완료`라고 말하지 않는다.
- `Statistical embedding 기반 Retrieval-Augmented Time-Series Evidence Layer MVP`라고 표현한다.
- 탄소 수치는 `estimated`로 표현한다.
- Grafana 화면 refresh는 30초지만, 백엔드 탐지는 5초 단위로 계속 수행된다고 설명한다.

