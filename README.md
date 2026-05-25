# inha_RADA

[![CI](https://github.com/Jjaerud/inha_RADA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Jjaerud/inha_RADA/actions/workflows/ci.yml)

**R**esource **A**nomaly **D**etection **A**gent — 연구실 PC 40대 규모 자원 모니터링 및
이상 탐지 플랫폼. 클라이언트가 5초 주기로 메트릭을 수집해 Spring Boot 수신 서버로 전송하고,
FastAPI ML 서버가 EDR 스타일 스코어링으로 채굴/노후화/오작동을 판정하며, Grafana 가 LAB-01
허니컴 대시보드로 상태를 시각화한다.

## 컴포넌트

| 컴포넌트 | 위치 | 비고 |
|----------|------|------|
| 클라이언트 (entry point: `client.py`) | `client.py`, `client_core/` | 호스트 OS 네이티브 실행. PyInstaller 단일 exe + Task Scheduler 로 학생 PC 백그라운드 운영. |
| 메인 서버 (Spring Boot) | `server-spring/` | Flyway V1~V8, API Key 인증 (SHA-256 pepper), ML 포워딩 |
| ML 서버 (FastAPI) | `ml_server/`, entry `ml_server.py` | scoring v0.8.0 (P0/P1/P2 적용) + 9-key `score_breakdown` + retrieval evidence 레이어 |
| Grafana 대시보드 | `infra/grafana/` | LAB-01 honeycomb (`marcusolsson-hexmap-panel`) + PC detail |
| 운영 배포 (NCP) | `docs/ncp_deployment.md` | Docker compose (`docker-compose.ncp.yml`) + NCP Cloud DB for PostgreSQL (managed) |

## 빠른 시작 (로컬 dev)

Docker Desktop 이 실행 중인 상태에서:

```powershell
Copy-Item .env.example .env          # 기본값으로 충분
docker compose up -d --build         # postgres + ml + spring + grafana (4 컨테이너)
Start-Process http://localhost:3000  # Grafana (rada_admin / .env 의 GF_SECURITY_ADMIN_PASSWORD)
```

- Spring health: 컨테이너 내부 `http://localhost:8081/actuator/health` (외부 8080 은 API)
- ML status: <http://localhost:8000/status>
- 클라이언트는 호스트에서 `python client.py` 로 별도 기동 (메트릭은 8080 으로 송신)

자세한 내용은 [`docs/docker-dev.md`](docs/docker-dev.md) 참고.

## 데모 시드 + 스모크

```powershell
# 40대 PC + pc-smoke 시드
Get-Content infra\seed\demo_data.sql -Raw `
  | docker compose exec -T postgres psql -U rada -d pc_monitor

# 채굴 시나리오 15회 전송 → anomaly_history 에 HIGH 누적되는지 확인
python tools\anomaly_trigger.py

# fast-path 회피 stealth 시나리오 (behavior-only mining 탐지)
python tools\stealth_trigger.py
```

`pc-smoke` 의 raw API key 는 `smoke-key` 이며 DB 컬럼에는
`SHA-256(API_KEY_PEPPER + ":" + raw_key)` 결과가 저장된다. dev pepper(`dev_pepper_change_me`)
이외의 값을 쓰면 시드의 해시값을 재계산해야 한다.

### 시드 PC 구분

| PC | 용도 | 인증 동작 |
|----|------|-----------|
| `PC-01` ~ `PC-40` | **시드 시점엔 Grafana 데모 데이터 전용** (md5 placeholder). 실제 운영 등록 시 `tools/provision_pcs.py` 로 SHA-256 해시 회전. | 시드 직후엔 401, provision 후 정상 |
| `pc-smoke` | **라이브 agent 인증 + anomaly 트리거 검증 전용** | `X-API-Key: smoke-key` 로 정상 동작 |
| `pc-stealth` | **stealth mining 트리거 전용** | `tools/provision_pcs.py` 로 별도 발급 |

실제 학생 PC 40대를 운영 등록할 때는 [`tools/provision_pcs.py`](tools/provision_pcs.py) 가 SHA-256 해시 형식으로 자동 등록한다. 절차: [`docs/pc-provisioning.md`](docs/pc-provisioning.md).

## 설정 (환경변수)

| 변수 | 용도 |
|------|------|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SCHEMA` | Spring/ML/Grafana 의 PostgreSQL 접속 |
| `DB_USER`, `DB_PASSWORD` | Spring DataSource & Flyway 마이그레이션 권한 |
| `API_KEY_PEPPER` | API Key 해싱 시 prefix (운영/dev 분리 필수) |
| `ML_SERVER_URL` | Spring → ML 포워딩 베이스 URL |
| `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD` | Grafana admin 계정 (운영 시 강한 무작위 값) |
| `ANTHROPIC_API_KEY` (선택) | AI agent 활성화 시 Claude API 키. 미설정이면 mock agent 사용. |

YAML 정책은 `ml_server/config_yaml/scoring_policy.yaml`, `ml_server/config_yaml/allowlist.yaml`
로 코드와 분리되어 있으며 ML 컨테이너의 `RADA_POLICY_DIR` 에 마운트된다.

## 테스트

| 스택 | 명령 | 규모 |
|------|------|------|
| Python | `pytest` | 79 test files (`tests/` 하위, 단위/통합) |
| Java | `cd server-spring && .\gradlew test` | Spring + Testcontainers |

## 배포

| 환경 | 방식 | 가이드 |
|---|---|---|
| 로컬/CI | `docker-compose.yml` (4 컨테이너 — postgres, ml-server, spring-server, grafana) | [`docs/docker-dev.md`](docs/docker-dev.md) |
| 운영 (NCP) | `docker-compose.ncp.yml` (3 컨테이너 — postgres 제외, Cloud DB managed 외부 연결) | [`docs/ncp_deployment.md`](docs/ncp_deployment.md) |
| 학생 PC (40대) | PyInstaller exe + Task Scheduler ONLOGON + 마에스트로 이미지 | [`docs/client_deployment.md`](docs/client_deployment.md) |
| 코드/대시보드/ML 변경 시 | `git push` → NCP `git pull` → `docker compose ... restart` | [`docs/deploy_updates.md`](docs/deploy_updates.md) |

PC 등록 / 키 회전 / 폐기: [`tools/provision_pcs.py`](tools/provision_pcs.py) (가이드: [`docs/pc-provisioning.md`](docs/pc-provisioning.md)).

## FP 시리즈 검증 결과

| 단계 | 환경 | metrics | anomaly | rate | 리포트 |
|---|---|---|---|---|---|
| Pre-P0/P1 | 로컬 | 7,364 | 4,853 | 65.9% | `docs/fp_field_analysis_v0.6.md` |
| P0+P1 | 로컬 | 3,343 | 54 | 1.6% | `docs/fp_field_analysis_post_p1.md` |
| P2 | 로컬 | 3,027 | 0 | 0% | `docs/fp_field_analysis_post_p2.md` |
| **NCP** | **NCP managed** | **4,432+** | **0** | **0.000%** | `docs/fp_field_analysis_ncp.md` |

mining 탐지력 (fast-path + stealth) 도 NCP 환경에서 즉시 발화 검증됨.

## 팀원 합류

신규 팀원은 한 줄 온보딩 스크립트로 dev 환경 준비:

```powershell
pwsh -File scripts/onboard.ps1
```

`.env` 복사 → docker compose up → 시드 적용 → anomaly smoke 까지 자동 수행. 실패 시 단계별 가이드를
출력한다. 기여 방법 / 브랜치 명명 / contract 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md) 참조.
`main` 보호 설정은 [`docs/branch-protection.md`](docs/branch-protection.md).

## 주요 문서 색인

### 처음 배포하는 사람은 이 순서대로 (작업 흐름)

1. **[`docs/github_setup.md`](docs/github_setup.md)** — Repo fork/clone, `.env` 준비, 로컬 dev 검증
2. **[`docs/ncp_deployment.md`](docs/ncp_deployment.md)** — NCP 콘솔 + App VM SSH + Docker compose + Flyway (실전 함정 포함)
3. **[`docs/client_deployment.md`](docs/client_deployment.md)** — PyInstaller 빌드 + install.bat + 마에스트로 case A
4. **[`docs/deployment_checklist.md`](docs/deployment_checklist.md)** — 학생 PC 40대 배포 체크리스트 (실습실 작업)
5. **[`docs/deploy_updates.md`](docs/deploy_updates.md)** — 운영 중 코드/Grafana/ML 변경 배포 워크플로우

### 운영 / 보조 문서

- [`docs/pc-provisioning.md`](docs/pc-provisioning.md) — API key 발급/회전 (provision_pcs.py)
- [`docs/team-guide.md`](docs/team-guide.md) — Fork 워크플로우 (팀 협업)
- [`docs/branch-protection.md`](docs/branch-protection.md) — main 보호 설정
- [`docs/docker-dev.md`](docs/docker-dev.md) — 로컬 docker compose dev 환경
- [`docs/grafana_cloud_dashboard_manual.md`](docs/grafana_cloud_dashboard_manual.md) — Grafana 패널 작업 매뉴얼

### 검증 리포트 (FP 시리즈)

- [`docs/fp_field_analysis_v0.6.md`](docs/fp_field_analysis_v0.6.md) — Pre-P0/P1 단계 (FP 65.9%)
- [`docs/fp_field_analysis_post_p1.md`](docs/fp_field_analysis_post_p1.md) — P0+P1 적용 후 (1.6%)
- [`docs/fp_field_analysis_post_p2.md`](docs/fp_field_analysis_post_p2.md) — P2 적용 후 (0%, 로컬)
- [`docs/fp_field_analysis_ncp.md`](docs/fp_field_analysis_ncp.md) — NCP 운영 환경 (0.000%, 최신)

### 알고리즘 / 백그라운드

- [`docs/retrieval_augmented_timeseries_manual.md`](docs/retrieval_augmented_timeseries_manual.md) — retrieval evidence 레이어
- [`docs/cryptojacking_detection_patterns.md`](docs/cryptojacking_detection_patterns.md) — 탐지 패턴 카탈로그
- [`docs/mcp-setup.md`](docs/mcp-setup.md) — Claude Code MCP 서버 설정
