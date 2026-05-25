# MCP Servers (GitHub / Postgres / Grafana)

Claude Code 가 RADA 프로젝트에서 GitHub 이슈/PR, dev DB, Grafana 대시보드를
직접 다루기 위한 MCP 서버 설정. `.mcp.json` 은 프로젝트 루트에 커밋되며,
실제 토큰은 `.env` (gitignored) 또는 사용자 환경변수로 주입한다.

## 1) 사전 준비

| 항목 | 필요 |
|---|---|
| Node.js | ≥ 18 (`npx` 사용) |
| Docker Desktop | Grafana MCP 컨테이너 실행용 |
| GitHub PAT | repo, read:org 권한 (classic) |
| Grafana API Key | Admin 권한, compose 기동 후 발급 |

## 2) `.env` 작성

`.env.example` 을 복사한 뒤 아래 3개 값만 채운다:

```
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
GRAFANA_URL=http://localhost:3000
GRAFANA_API_KEY=glsa_...
```

Postgres MCP 는 `POSTGRES_USER/PASSWORD/DB` 를 자동 재사용한다.

## 3) 등록된 서버

| 이름 | 패키지 | 동작 |
|---|---|---|
| `github` | `@modelcontextprotocol/server-github` (npx) | inha_RADA 이슈/PR/파일 조회·생성 |
| `postgres` | `@modelcontextprotocol/server-postgres` (npx) | dev DB 스키마·쿼리 (read-only) |
| `grafana` | `mcp/grafana` (docker image) | 대시보드·패널·쿼리 조작 |

`.mcp.json` 의 `${VAR}` 는 Claude Code 가 자동으로 환경변수 치환한다.

## 4) 최초 실행 순서

```powershell
# 1) compose 기동 (postgres + grafana 가 떠 있어야 MCP 가 연결 가능)
docker compose up -d

# 2) Grafana API key 발급 후 .env 에 기입
start http://localhost:3000/org/apikeys

# 3) Claude Code 재시작 → .mcp.json 자동 로드
```

Claude Code 재시작 후 첫 사용 시 각 MCP 서버 승인 프롬프트가 뜨면 Allow.

## 5) 확인용 프롬프트 예시

- GitHub: "inha_RADA 의 최근 PR 5개 보여줘"
- Postgres: "anomaly_history 테이블 최근 10건 verdict 컬럼별로 카운트"
- Grafana: "rada-main 대시보드의 패널 목록"

## 6) 트러블슈팅

- `Error: GITHUB_PERSONAL_ACCESS_TOKEN is not set` → `.env` 확인 후 Claude Code 재시작
- Postgres `connection refused` → `docker compose ps` 로 postgres healthy 인지 확인
- Grafana MCP `pull access denied` → `docker pull mcp/grafana` 수동 시도 후 재실행
