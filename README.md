# inha_RADA

**R**esource **A**nomaly **D**etection **A**gent — 연구실 PC 40대 규모 자원 모니터링 및
이상 탐지 플랫폼. 클라이언트가 5초 주기로 메트릭을 수집해 Spring Boot 수신 서버로 전송하고,
FastAPI ML 서버가 EDR 스타일 스코어링으로 채굴/노후화/오작동을 판정하며, Grafana 가 LAB-01
허니컴 대시보드로 상태를 시각화한다.

## 컴포넌트

| 컴포넌트 | 위치 | 비고 |
|----------|------|------|
| 클라이언트 (entry point: `client.py`) | `client.py`, `client_core/` | 호스트 OS 네이티브 실행. `agent.py` 는 더 이상 사용하지 않음. |
| 메인 서버 (Spring Boot) | `server-spring/` | Flyway V1~V7, API Key 인증, ML 포워딩 |
| ML 서버 (FastAPI) | `ml_server/`, entry `ml_server.py` | scoring v0.5.0 + 9-key `score_breakdown` + retrieval evidence 레이어 |
| Grafana 대시보드 | `infra/grafana/` | LAB-01 honeycomb (`marcusolsson-hexmap-panel`) + PC detail |
| 운영 배포 (NCP) | `infra/ncp/` | systemd 네이티브 (Docker 미사용) |

## 빠른 시작 (로컬 dev)

Docker Desktop 이 실행 중인 상태에서:

```powershell
Copy-Item .env.example .env          # 기본값으로 충분
docker compose up -d --build         # postgres + ml + spring + grafana
Start-Process http://localhost:3000  # Grafana (admin / admin)
```

- Spring health: <http://localhost:8080/actuator/health>
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
```

`pc-smoke` 의 raw API key 는 `smoke-key` 이며 DB 컬럼에는
`SHA-256(API_KEY_PEPPER + ":" + raw_key)` 결과가 저장된다. dev pepper(`dev_pepper_change_me`)
이외의 값을 쓰면 시드의 해시값을 재계산해야 한다.

## 설정 (환경변수)

| 변수 | 용도 |
|------|------|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SCHEMA` | Spring/ML/Grafana 의 PostgreSQL 접속 |
| `DB_USER`, `DB_PASSWORD` | Spring DataSource & Flyway 마이그레이션 권한 |
| `API_KEY_PEPPER` | API Key 해싱 시 prefix (운영/dev 분리 필수) |
| `ML_SERVER_URL` | Spring → ML 포워딩 베이스 URL |

YAML 정책은 `ml_server/config_yaml/scoring_policy.yaml`, `ml_server/config_yaml/allowlist.yaml`
로 코드와 분리되어 있으며 ML 컨테이너의 `RADA_POLICY_DIR` 에 마운트된다.

## 테스트

| 스택 | 명령 | 규모 |
|------|------|------|
| Python | `pytest` | 248 cases (`tests/` 하위, 단위/통합) |
| Java | `cd server-spring && .\gradlew test` | 67 단위 케이스 |

## 배포

- 로컬/CI: `docker-compose.yml` (4 컨테이너 — postgres, ml-server, spring-server, grafana).
- 운영(NCP): `infra/ncp/systemd/*.service` 로 동일 호스트에 네이티브 기동. Docker compose 파일은
  운영 경로에서 참조되지 않는다.

## 라이선스 / 팀

- 라이선스: TBD (사내 연구용 — 외부 공개 전 협의 필요).
- 유지보수: 인하대학교 컴퓨터공학과 종합설계 RADA 팀. 문의는 저장소 이슈로 접수한다.
