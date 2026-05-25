# RADA NCP 인프라 — 운영 가이드

> **현재 운영 방식 (2026-05 이후)**: Docker compose (`docker-compose.ncp.yml`) + NCP Cloud DB for PostgreSQL (managed) 조합.
> 본 디렉터리의 systemd / 자가 설치 postgres 자료는 **레거시 (deprecated)** 로, 더 이상 운영 경로에서 참조되지 않는다.

## 현재 운영 — 두 단계로 진행

### 1. 서버 셋업 (1회)

NCP 콘솔 작업 + App VM SSH 셋업: [`docs/guides/ncp_deployment.md`](../../docs/guides/ncp_deployment.md)

요약:
- App VM (Ubuntu 22.04, 4vCPU/16GB) — Docker compose 로 Spring + ML + Grafana 호스팅
- Cloud DB for PostgreSQL (managed, 15.x) — pc_monitor DB + rada user + 사설 도메인
- ACG: 22 (관리자 IP), 8080 (학생 PC 출구 / PoC 0.0.0.0/0), 3000 (관리자 + 학내망), 5432 (App VM 내부만)
- Flyway V1~V8 첫 부팅 시 자동 적용

### 2. 클라이언트 배포 (학생 PC 40대)

- API key 발급: [`docs/reference/pc-provisioning.md`](../../docs/reference/pc-provisioning.md)
- PyInstaller exe + Task Scheduler: [`docs/guides/client_deployment.md`](../../docs/guides/client_deployment.md)
- 마에스트로 이미지 환경 절차 포함 체크리스트: [`docs/guides/deployment_checklist.md`](../../docs/guides/deployment_checklist.md)

### 3. 운영 중 변경사항 배포

코드 / 대시보드 / scoring policy / ML 알고리즘 수정 시:
[`docs/guides/deploy_updates.md`](../../docs/guides/deploy_updates.md)

## 본 디렉터리의 자산 — 운영 영향 없음 (legacy)

| 경로 | 현재 운영에 사용? |
|---|---|
| `scripts/01-acg-setup.md` | 참고용 (실제 ACG 룰은 `docs/guides/ncp_deployment.md` §1 기준) |
| `scripts/02-install-postgres.sh` | ❌ Cloud DB managed 사용 — 자가 postgres 설치 안 함 |
| `scripts/03-create-grafana-reader.sh` | ❌ Cloud DB managed 의 user 권한 모델로 대체 |
| `scripts/04-install-jdk-grafana.sh` | ❌ Docker 컨테이너로 대체 |
| `scripts/05-timezone-setup.sh` | 참고용 (Docker 컨테이너 TZ=Asia/Seoul 로 처리) |
| `systemd/*.service` | ❌ systemd 네이티브 운영 안 함 |
| `logrotate/rada` | ❌ Docker 로그 드라이버로 대체 |

위 파일들은 **저장소 히스토리 보존 + 향후 비-Docker 환경 참고용** 으로 유지된다.

## Quick reference

| 작업 | 명령 |
|---|---|
| 컨테이너 상태 | `docker compose -f /opt/rada/docker-compose.ncp.yml ps` |
| Spring 로그 | `docker compose -f /opt/rada/docker-compose.ncp.yml logs -f spring-server` |
| ML 로그 | `docker compose -f /opt/rada/docker-compose.ncp.yml logs -f ml-server` |
| 코드 업데이트 | `cd /opt/rada && git pull && docker compose -f docker-compose.ncp.yml up -d --build` |
| Grafana 재시작 (대시보드만 갱신) | `docker compose -f /opt/rada/docker-compose.ncp.yml restart grafana` |
| DB 접속 | `PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME"` |

`.env` 환경변수 (App VM `/opt/rada/.env`):

```
DB_HOST=<Cloud DB Private Domain 또는 IP>
DB_PORT=5432
DB_NAME=pc_monitor
DB_USER=rada
DB_PASSWORD=<강한 비밀번호>
DB_SCHEMA=pc_monitor
API_KEY_PEPPER=<강한 무작위 hex>
GF_SECURITY_ADMIN_USER=rada_admin
GF_SECURITY_ADMIN_PASSWORD=<강한 무작위>
ANTHROPIC_API_KEY=<선택 — AI agent 활성화 시>
```

## Retention (40 PC 대응)

40 PC × 5초 주기 = 약 1.4 GB/일. 14일 retention 으로 약 20 GB 유지. NCP VM crontab:

```bash
0 3 * * * /opt/rada/tools/cleanup_old_data.sh >> /var/log/rada-cleanup.log 2>&1
```

스크립트: `/opt/rada/tools/cleanup_old_data.sh` (이미 등록). 14일 metrics + 90일 anomaly/AI 판단 보존.

Cloud DB 스토리지는 **최소 30GB** 권장 (10GB 면 1주일 만에 가득).

## FP 검증 결과 (NCP 환경)

`docs/analysis/fp_field_analysis_ncp.md` — 정상 사용 7h39m / FP 0건, mining 탐지 (fast-path + stealth) 즉시 발화.

4단계 누적:
- Pre-P0/P1: 65.9% → P0+P1: 1.6% → P2 로컬: 0% → **NCP 운영: 0.000%** ✓
