# Contributing to RADA

3명 팀이 GitHub 통해 협업하는 가벼운 절차. 무거운 governance 보다 **회귀 0** 과 **contract 보호** 가 우선.

## Quick start

```powershell
git clone <repo-url>
cd rada
Copy-Item .env.example .env          # 기본값으로 충분
docker compose up -d --build         # postgres + ml + spring + grafana
python tools\anomaly_trigger.py      # smoke: HIGH anomaly_history 누적 확인
```

또는 한 줄: `pwsh -File scripts/onboard.ps1`.

자세한 dev 가이드는 [`docs/docker-dev.md`](docs/docker-dev.md), 운영(NCP) 은 [`infra/ncp/`](infra/ncp/).

## Branch 전략

- `main` 은 보호 브랜치. **직접 push 금지**, PR 1 review + CI 통과 필수.
- 작업 브랜치 이름:
  - `feat/<short-desc>` — 신규 기능
  - `fix/<short-desc>` — 버그 수정
  - `docs/<short-desc>` — 문서만
  - `chore/<short-desc>` — 빌드/CI/도구
- Conventional Commits 메시지:
  - `feat(spring): add /actuator/foo`
  - `fix(ml): handle empty signals_missing`
  - `docs(grafana): update hexmap legend`
  - scope 권장: `client` / `spring` / `ml` / `grafana` / `ops` / `docs`

## 테스트 정책

PR 올리기 **전 로컬**에서:

```powershell
pytest                                       # 목표: 282+ pass
cd server-spring; .\gradlew test --tests "*Test"   # 목표: 77 pass (단위)
```

- CI (`.github/workflows/ci.yml`) 가 PR 마다 같은 명령을 다시 돌린다. 둘 다 통과해야 머지 가능.
- Testcontainers 통합 6건은 Docker 가 필요하므로 CI 에서 스킵, **로컬에서 본인이 확인**.
- 신규 기능에는 단위 테스트 **1개 이상** 권장 (없을 사유는 PR 본문에 명시).

## Contract — 절대 금지 / 합의 필요 / 자유

### 절대 금지 (팀 전원 동의 + 마이그레이션 계획 없이는 금지)
- 기존 Flyway `V1`~`V8` SQL 파일 내용 수정 (드리프트 → 머신 단위 데이터 손실 위험)
- `MetricsRequest` 22-key payload 의 필드 이름/타입 변경
- `/api/metrics`, `/analyze`, `/actuator/health|prometheus|info` 경로 변경
- `ApiKeyHasher` 알고리즘 (`SHA-256(pepper + ":" + raw)`) 변경
- Grafana datasource UID `rada_pg`, `rada_spring`

### 합의 필요 (PR Contract 체크리스트 사용)
- `MlResponse` / `analyze_router` 응답 JSON 키 추가/이름 변경
- `anomaly_history.scores` JSONB nested key 이름
- 환경변수 이름, Docker compose service 이름
- 신규 Flyway `V9+` 추가 (스키마 충돌 확인용)

### 자유 (담당 모듈 안에서)
- **client** (`client.py`, `client_core/`): 수집기 내부 구현, 재시도/큐 정책, 로깅
- **spring** (`server-spring/`): 내부 서비스 클래스, 메트릭 추가, 비즈니스 로직 — payload/응답 스키마만 안 건드리면 자유
- **ml** (`ml_server/`): 스코어링 알고리즘, retrieval/EDR 내부 — `analyze` 응답 스키마만 유지하면 자유
- **grafana** (`infra/grafana/`): 패널 추가/배치 변경 — datasource UID 만 유지
- **ops** (`infra/`, `docker-compose.yml`): 신규 서비스 추가, 헬스체크 — 기존 service 이름 유지

## 시크릿 관리

- `.env`, `claude_desktop_config.json`, API 토큰류는 **절대 commit 금지** (`.gitignore` 에 등록됨).
- 토큰이 노출되면 **즉시 revoke + 새 발급**, 노출된 commit 은 force-rewrite 보다 새 키 발급이 우선.
- `API_KEY_PEPPER` 는 dev (`dev_pepper_change_me`) 와 prod 분리. prod pepper 는 Vault/secret manager 사용 (현재는 NCP env 파일).
- 시드의 API key 해시 (`md5('demo-key-' || N)`, `SHA-256(pepper + ":smoke-key")`) 는 dev 전용이며 prod 에 반입 금지.

## Merge 방식

- PR 머지는 **squash merge** 권장 — main history 한 줄로 깔끔.
- `main` 에 **force push 금지**.
- 머지 후 작업 브랜치는 즉시 삭제 (GitHub UI 자동 삭제 권장 설정).

## PR 작성 팁

- 1 PR = 1 의도. 리팩터링과 신규 기능을 섞지 말 것.
- `.github/pull_request_template.md` 의 Contract 체크리스트를 정직하게 표시.
- 라이브 검증한 명령/출력은 PR 본문에 붙여놓으면 리뷰 시간 절약.
- Grafana 변경은 패널 캡처 1장 첨부.

## 질문 / 막힘

- 30분 이상 막히면 팀 채팅으로 상황 공유. 디버깅은 페어로.
- 회귀 발견 시 `[BUG]` 이슈 먼저 등록 → 작업 브랜치.
