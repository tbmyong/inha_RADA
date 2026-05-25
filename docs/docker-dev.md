# RADA 로컬 Docker 개발 환경

> 이 문서는 **로컬 dev/test 전용**입니다. NCP 운영 배포는 별도 (`docker-compose.ncp.yml` + Cloud DB managed).
> NCP 운영 절차는 [`ncp_deployment.md`](ncp_deployment.md) 참조.

## 구성 요소 (Client 제외)

| 서비스 | 포트(호스트) | 컨테이너 | 비고 |
|--------|------|---------|------|
| postgres | 25432 | rada-postgres | named volume `rada_pgdata`. Windows Hyper-V 예약 포트 회피로 25432 매핑 |
| ml-server | 8000 | rada-ml | FastAPI, `RADA_POLICY_DIR=/app/ml_server/config_yaml` |
| spring-server | 8080 | rada-spring | Flyway V1~V8 자동 실행, profile=`docker` |
| grafana | 3000 | rada-grafana | 대시보드 + 데이터소스 provisioning 자동 로드 |

> Client(`client.py`)는 호스트 OS에서 네이티브로 실행해 `http://localhost:8080`으로 메트릭을 전송합니다.

## 빠른 시작 (Windows PowerShell)

```powershell
# 1. 환경변수 파일 준비
Copy-Item .env.example .env

# 2. 빌드 + 백그라운드 기동
docker compose up -d --build

# 3. 상태 확인
docker compose ps
```

기동 후:
- Grafana: <http://localhost:3000> (`admin` / `.env` 의 `GF_SECURITY_ADMIN_PASSWORD`)
- Spring API: <http://localhost:8080/actuator/health>
- ML API: <http://localhost:8000/status>

## DB 접속

```powershell
docker compose exec postgres psql -U rada -d pc_monitor
# 스키마 확인
\dn
# Flyway 이력
SELECT version, description, success FROM pc_monitor.flyway_schema_history;
```

## 로그

```powershell
docker compose logs -f spring-server
docker compose logs -f ml-server
docker compose logs --tail=100 postgres
```

## 정지 / 초기화

```powershell
# 정지(데이터 보존)
docker compose down

# 정지 + 볼륨 삭제 (DB / Grafana 초기화)
docker compose down -v
```

## YAML 검증 (빌드 없이)

```powershell
docker compose config
```

## NCP 운영과의 분리

- 본 compose는 프로젝트 루트의 `docker-compose.yml` 하나로 완결됩니다.
- `infra/ncp/systemd/*.service`, `infra/ncp/scripts/*` 는 수정하지 않았습니다.
- Grafana 데이터소스 provisioning 도 `infra/grafana/provisioning/datasources/postgres.yaml`(NCP용, `127.0.0.1` + `grafana_reader`) 은 그대로 두고, 컨테이너에는 `infra/grafana/provisioning-docker/datasources/postgres.yaml`(`postgres:5432`)을 별도 마운트합니다. UID 는 `rada_pg` 로 동일해 대시보드를 공유합니다.
- DB 스키마는 Flyway V1~V7 까지 적용됩니다. V6 는 `rada` role 에 한정된 search_path 설정이었고, V7 은 `${db_user}` / `${db_schema}` placeholder 로 매개변수화된 동일 설정이므로 운영자가 `POSTGRES_USER` / `DB_SCHEMA` 를 바꿔도 그대로 동작합니다 (placeholder 는 `application.yml` 의 `spring.flyway.placeholders` 에 매핑됨).

## 시드 데이터 + 스모크 테스트

```powershell
# 1) 데모 시드 (PC-01~PC-40 + pc-smoke) 적용
Get-Content infra\seed\demo_data.sql -Raw `
  | docker compose exec -T postgres psql -U rada -d pc_monitor

# 2) anomaly 트리거 (15회 채굴 시나리오 전송)
python tools\anomaly_trigger.py
```

`pc-smoke` 의 `api_key` 컬럼은 `SHA-256(pepper + ":" + "smoke-key")` 해시값을
저장하므로 `.env` 의 `API_KEY_PEPPER` 를 변경하면 해당 줄을 재해시해야 합니다
(dev 기본 pepper: `dev_pepper_change_me`). 15/15 OK 응답을 받으면 메인 서버 →
ML 서버 → `anomaly_history` 까지 통합 흐름이 검증된 상태입니다.
