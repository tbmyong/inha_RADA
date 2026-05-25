# RADA 문서 색인

문서는 용도별로 3개 폴더로 분류돼 있다.

```
docs/
├── guides/      ← 작업 순서대로 따라가는 step-by-step 가이드 (5개)
├── reference/   ← 운영 / 협업 / 알고리즘 참고 (8개)
└── analysis/    ← FP 검증 리포트 (시계열, 4개)
```

---

## 📘 guides/ — 작업 순서대로

처음 배포하는 사람은 이 순서대로 따라가면 됨. 각 문서 상단에 **이전/다음 단계 하이퍼링크** 가 있어서 흐름을 잃지 않는다.

| 순서 | 문서 | 소요 | 내용 |
|---|---|---|---|
| 1 | [`github_setup.md`](guides/github_setup.md) | ~10분 | Repo fork/clone, `.env` 준비, 로컬 dev 검증 |
| 2 | [`ncp_deployment.md`](guides/ncp_deployment.md) | ~75분 | NCP 콘솔 + App VM SSH + Docker compose + Flyway (실전 함정 14건 포함) |
| 3 | [`client_deployment.md`](guides/client_deployment.md) | ~85분 | PyInstaller 빌드 + install.bat + 마에스트로 case A (함정 12건 포함) |
| 4 | [`deployment_checklist.md`](guides/deployment_checklist.md) | ~45분 | 학생 PC 40대 배포 체크리스트 (실습실 작업) |
| 5 | [`deploy_updates.md`](guides/deploy_updates.md) | 변경 시 | 운영 중 코드/Grafana/ML 변경 배포 워크플로우 |

전체 소요 (처음 1회): 약 3.5시간 + 학생 PC 1대당 1분.

---

## 📗 reference/ — 운영 / 협업 참고

작업 중 필요할 때 찾아보는 lookup 자료.

### 운영 도구
- [`pc-provisioning.md`](reference/pc-provisioning.md) — API key 발급/회전 (`tools/provision_pcs.py`)
- [`docker-dev.md`](reference/docker-dev.md) — 로컬 docker compose dev 환경 상세

### 팀 협업
- [`team-guide.md`](reference/team-guide.md) — Fork 워크플로우 + 일반 규약
- [`branch-protection.md`](reference/branch-protection.md) — main 브랜치 보호 설정
- [`mcp-setup.md`](reference/mcp-setup.md) — Claude Code MCP 서버 설정 (선택)

### 알고리즘 / 디자인
- [`grafana_cloud_dashboard_manual.md`](reference/grafana_cloud_dashboard_manual.md) — 대시보드 시각화 + 패널 작업 매뉴얼
- [`retrieval_augmented_timeseries_manual.md`](reference/retrieval_augmented_timeseries_manual.md) — retrieval evidence 레이어 명세
- [`cryptojacking_detection_patterns.md`](reference/cryptojacking_detection_patterns.md) — 31-pattern mining 탐지 카탈로그

---

## 📕 analysis/ — FP 검증 리포트 (시계열)

알고리즘 진화 단계마다 측정한 false-positive 검증 결과. 시간순.

| 단계 | 환경 | metrics | anomaly | rate | 리포트 |
|---|---|---|---|---|---|
| Pre-P0/P1 | 로컬 | 7,364 | 4,853 | 65.9% | [`fp_field_analysis_v0.6.md`](analysis/fp_field_analysis_v0.6.md) |
| P0+P1 | 로컬 | 3,343 | 54 | 1.6% | [`fp_field_analysis_post_p1.md`](analysis/fp_field_analysis_post_p1.md) |
| P2 | 로컬 | 3,027 | 0 | 0% | [`fp_field_analysis_post_p2.md`](analysis/fp_field_analysis_post_p2.md) |
| **NCP** | **NCP managed** | **4,432+** | **0** | **0.000%** ✓ | [`fp_field_analysis_ncp.md`](analysis/fp_field_analysis_ncp.md) (최신) |

mining 탐지력 (fast-path + stealth) 도 NCP 환경에서 즉시 발화 검증됨 (`fp_field_analysis_ncp.md` §5 참조).

---

## 작업 흐름 (전체 도식)

```
┌─────────────────────────────────────────────────────────────┐
│  처음 배포  (one-time)                                       │
│                                                              │
│  guides/github_setup.md                                      │
│       ↓                                                      │
│  guides/ncp_deployment.md   ← 함정 14건 포함                │
│       ↓                                                      │
│  guides/client_deployment.md  ← 함정 12건 포함              │
│       ↓                                                      │
│  guides/deployment_checklist.md                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  운영 중 변경 (반복)                                          │
│                                                              │
│  guides/deploy_updates.md                                    │
│       │                                                      │
│       ├─ Grafana 패널: restart grafana 만                   │
│       ├─ Scoring yaml:  restart ml-server                   │
│       ├─ Spring 코드:   up -d --build spring-server         │
│       ├─ ML 코드:       up -d --build ml-server             │
│       └─ Client 코드:   exe 재빌드 + 학생 PC 재배포          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 참고

- 루트 [`../README.md`](../README.md) — 프로젝트 전체 개요
- 루트 [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — 기여 가이드 (커밋 / PR 규칙)
- [`../client_core/README.md`](../client_core/README.md) — 클라이언트 모듈 구조
- [`../server-spring/README.md`](../server-spring/README.md) — Spring 빌드 + Flyway
- [`../infra/grafana/README.md`](../infra/grafana/README.md) — Grafana 대시보드 구조
- [`../infra/ncp/README.md`](../infra/ncp/README.md) — NCP 운영 quick reference
- [`../infra/seed/README.md`](../infra/seed/README.md) — 데모 시드 (dev 전용)
