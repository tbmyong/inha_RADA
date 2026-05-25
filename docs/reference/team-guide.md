# RADA 팀 협업 가이드

본 가이드는 RADA 프로젝트를 다인 협업으로 개선하는 워크플로를 정리한다.

**전제**:
- 본 repo (`Jjaerud/inha_RADA`) 는 **upstream** — 통합 지점
- 각 팀원은 본 repo 를 자기 GitHub 계정으로 **fork** 해서 작업
- 본 repo 에 직접 push 권한은 maintainer 1명만 가짐
- 변경은 모두 **fork → PR → 리뷰 → squash merge** 흐름

```
Jjaerud/inha_RADA (upstream)            <- 통합 지점
    │
    │ (fork)
    ▼
<teammate-A>/inha_RADA                   <- A 의 작업 공간
<teammate-B>/inha_RADA                   <- B 의 작업 공간
<teammate-C>/inha_RADA                   <- C 의 작업 공간
```

---

## 1. 최초 셋업 (15분)

### 1-1. Fork

1. GitHub 웹에서 https://github.com/Jjaerud/inha_RADA 접속
2. 우상단 **Fork** → 본인 계정으로 fork 생성
3. "Copy the main branch only" 체크 (다른 브랜치 없음)

### 1-2. Clone + 원격 연결

```powershell
# 본인 fork 를 clone
git clone https://github.com/<your-github-id>/inha_RADA.git rada
cd rada

# upstream (본 repo) 을 추가 원격으로 등록
git remote add upstream https://github.com/Jjaerud/inha_RADA.git

# 확인
git remote -v
# origin    https://github.com/<your-github-id>/inha_RADA.git
# upstream  https://github.com/Jjaerud/inha_RADA.git
```

### 1-3. 사전 설치

| 항목 | 권장 버전 |
|---|---|
| Python | 3.11 |
| Java JDK | 17 |
| Docker Desktop | 최신 (WSL2 백엔드) |
| Node.js LTS | (선택) MCP 사용 시 |

### 1-4. 환경 변수

```powershell
Copy-Item .env.example .env
```

`.env` 의 기본값으로 dev 환경 충분. `API_KEY_PEPPER=dev_pepper_change_me` 가 시드 해시와 매칭됨 — 변경 시 시드 인증 깨짐.

### 1-5. Docker compose 기동

```powershell
docker compose up -d --build
```

첫 빌드 5~10분 (Spring multi-stage + ML 의존성). 끝나면:

```powershell
docker compose ps
```

4 컨테이너 (`postgres`, `ml-server`, `spring-server`, `grafana`) 모두 `Up (healthy)` 면 정상.

### 1-6. 시드 + 스모크

```powershell
# 데모 PC + 인증 가능한 pc-smoke 등록
docker compose exec -T postgres sh -c "psql -U rada -d pc_monitor -f /tmp/seed.sql"
# (위가 실패하면 docker cp 로 시드 파일 먼저 복사)
docker cp infra\seed\demo_data.sql rada-postgres:/tmp/seed.sql
docker compose exec -T postgres sh -c "psql -U rada -d pc_monitor -f /tmp/seed.sql"

# mining 시나리오 트리거
python tools\anomaly_trigger.py
```

15/15 OK 나오면 환경 준비 완료.

### 1-7. Grafana 확인

http://localhost:3000 (admin / admin) → Dashboards → RADA → rada-main / rada-pc-detail

---

## 2. 데이터 격리 (자주 헷갈리는 부분)

**팀원 간 Docker 컨테이너 데이터는 공유되지 않는다.** 각자 본인 PC 의 Docker 가 별도 volume 을 만들어 사용.

| 자원 | 어디에 있는가 |
|---|---|
| Postgres data (`rada_pgdata`) | 본인 PC 의 Docker volume |
| `metrics_history`, `anomaly_history`, `ai_judgment_history` | 본인 PC 한정 |
| Grafana dashboard state | 본인 PC 한정 |
| `.env` 토큰 | 본인 PC 한정 (gitignore) |

**공유되는 것**: GitHub 의 코드/yaml/JSON 만.

따라서:
- 팀원 A 가 자기 PC 에서 anomaly_trigger 100번 돌려도 다른 팀원 DB 영향 X
- 본인이 `docker compose down -v` 해도 본인 데이터만 날아감
- 정해진 baseline 비교가 필요하면 `infra/seed/demo_data.sql` 같은 시드를 commit 해서 공유

---

## 3. 작업 사이클 (모든 변경에 적용)

### 3-1. 작업 시작 전 — upstream 동기화

```powershell
git checkout main
git fetch upstream
git merge upstream/main --ff-only
git push origin main
```

`--ff-only` 가 실패한다는 건 본인이 main 에 직접 commit 한 적이 있다는 뜻 — **본인 fork main 에 직접 commit 금지**. 모든 작업은 별도 브랜치에서.

### 3-2. 작업 브랜치 생성

```powershell
git checkout -b feat/<my-short-desc>
```

### 3-3. 작성 + commit

작은 단위로 자주 commit. Conventional Commits 메시지:

```
feat(scope): 새 기능
fix(scope): 버그 수정
docs(scope): 문서
refactor(scope): 동작 변경 없는 리팩터링
test(scope): 테스트
chore(scope): 빌드/CI/의존성

scope 예시: client / spring / ml / grafana / ops / docs / tools
```

### 3-4. upstream 변경이 들어왔으면 rebase

작업 도중 upstream main 에 새 변경이 머지되면:

```powershell
git fetch upstream
git rebase upstream/main
# 충돌 발생 시 해결 → git add → git rebase --continue
# 또는 전체 취소: git rebase --abort
```

### 3-5. 로컬 검증

```powershell
python -m pytest --tb=line -q
cd server-spring
.\gradlew test --tests "*Test"
cd ..
```

Python / Java 단위 테스트 모두 통과 + 신규 테스트 1+ 추가가 일반적.

### 3-6. Push + PR

```powershell
git push -u origin feat/<my-short-desc>
# rebase 했으면 강제 push 필요:
# git push --force-with-lease origin feat/<my-short-desc>
```

GitHub 의 본인 fork → "Contribute" → "Open pull request":
- base: `Jjaerud/inha_RADA` / `main`
- compare: `<your-fork>/inha_RADA` / `feat/<my-short-desc>`
- 디스크립션: PR 템플릿 채우기

### 3-7. 머지 후

maintainer 가 squash merge 한 뒤:

```powershell
git checkout main
git fetch upstream
git merge upstream/main --ff-only
git push origin main
git branch -d feat/<my-short-desc>
git push origin --delete feat/<my-short-desc>
```

---

## 4. 역할별 작업 영역

### 4-1. ML / scorer 담당

**손대도 되는 곳** (자유):
- `ml_server/scorer/*` — 신호 추출, 점수 계산, verdict 분류, context discount
- `ml_server/scorer/pattern_categories.py` — Resource/Network/System evaluator
- `ml_server/scorer/category_gating.py` — 게이팅 임계
- `ml_server/detector/anomaly_predictor.py` — IF/LOF 파라미터
- `ml_server/feature/feature_builder.py` — 10차원 feature
- `ml_server/retrieval/*` — embedding/store/evidence
- **`ml_server/config_yaml/scoring_policy.yaml`** — 임계값 튜닝
- **`ml_server/config_yaml/allowlist.yaml`**

**손대지 말 것** (contract):
- `ml_server/model/requests.py` 의 기존 22-key 필드
- `ml_server/api/analyze_router.py` 응답의 기존 top-level 키 이름
- `scoring_policy.yaml` 의 `version` 형식 (`scoring-vX.Y.Z`)

**PR 전 체크리스트**:
- [ ] Python 테스트 통과 + 신규 1+
- [ ] `python tools/anomaly_trigger.py` 후 anomaly_history HIGH 보존
- [ ] 본인 PC 정상 traffic 데이터로 FP rate 측정 → PR 디스크립션에 첨부

### 4-2. 대시보드 담당

**손대도 되는 곳**:
- `infra/grafana/provisioning/dashboards/*.json` — 패널 추가/SQL/색감/레이아웃
- 새 dashboard 파일 추가 (예: `rada-team-X.json`)
- `infra/grafana/grafana.ini` (조심)

**손대지 말 것**:
- `infra/grafana/provisioning/datasources/*.yaml` 의 `uid: rada_pg`
- `infra/grafana/provisioning-docker/datasources/*.yaml` 의 `uid`

**동시 작업 안전 전략**:
- 동일 dashboard JSON 을 여러 명이 수정하면 거의 항상 충돌.
- 가능하면 **새 dashboard 파일** 로 분리. `rada-main.json` 직접 수정은 자제.

**필수 룰 — P0-3 (gating) 이후 score / verdict 분리 표시**

P0-3 도입 후 `scores.final` 과 `verdict` / `overall_severity` 가 일치하지 않을 수 있다. 예: `scores.final = 12` 인데 gating 차단으로 `verdict = OBSERVE / severity = LOW`. 운영자가 점수만 보면 혼란 → **`scores.final` 표시하는 모든 패널에서 `evidence_meta.promotion_gated` + `promotion_reason` 같이 노출**.

상세 규칙 + 권장 SQL 은 [`docs/fp_field_analysis_v0.6.md`](fp_field_analysis_v0.6.md) §7-P0-3 의 "Gating 도입 부작용" 절 참고.

**PR 전 체크리스트**:
- [ ] `docker compose restart grafana` 후 패널 정상 로드 확인
- [ ] datasource UID `rada_pg` / `rada_spring` 만 사용
- [ ] **`scores.final` 표시 패널에 `promotion_gated` + `promotion_reason` 동반 노출**
- [ ] 점수 기준 정렬 패널은 `promotion_gated = false` 필터 또는 verdict 우선 정렬
- [ ] PR 에 패널 스크린샷 첨부

### 4-3. 클라이언트 / 수집 담당

**손대도 되는 곳**:
- `client_core/collector/*` — 수집 로직 내부
- `client_core/detector/*` — 로컬 탐지기
- `client_core/sender/*` — 송신 로직
- `client_core/identity/*`
- `client_core/runtime/*`

**손대지 말 것**:
- `client_core/model/payload.py` 의 `ML_PAYLOAD_KEYS` 22개
- `client.py` shim 의 legacy 함수 시그니처

### 4-4. 인프라 / 운영 담당

**손대도 되는 곳**:
- `infra/ncp/*` — 운영 systemd / 설치 스크립트
- `tools/*`
- `docker-compose.yml` (조심, 영향 큼)

**손대지 말 것**:
- `docker-compose.yml` 의 service 이름 (`postgres`, `ml-server`, `spring-server`, `grafana`)
- Dockerfile 의 expose port 번호

---

## 5. Contract — 절대 협의 없이 건드리지 말 것

본 항목은 **누군가 한 명이 바꾸면 다른 영역 전부 깨짐**. 변경 필요 시 반드시 사전 협의 + 전원 동의:

| Contract | 영향 받는 파일 |
|---|---|
| 22-key Agent payload | `client_core/model/payload.py` + `server-spring/.../MetricsRequest.java` + `ml_server/model/requests.py` |
| ML 응답 top-level 키 (`overall_severity`, `verdict`, `scores`, `score_breakdown` 9키, `alerts`, `retrieval_evidence`, `signals_missing`, `category_signals`, `policy_version`) | `ml_server/api/analyze_router.py` + `server-spring/.../MlResponse.java` + Grafana SQL |
| `anomaly_history.scores` JSONB 안 nested key 이름 | ML server + Spring `AlertService.java` + Grafana SQL |
| API 경로 (`/api/metrics`, `/analyze`, `/actuator/*`, `/status`, `/admin/*`, `/history/{pc_id}`) | controller/router 코드 |
| 인증 알고리즘 SHA-256(pepper + ":" + raw) | `ApiKeyHasher.java` + `tools/provision_pcs.py` |
| Flyway 기존 V*.sql (V1~V8) | `server-spring/.../db/migration/` |
| Docker compose service 이름 | `docker-compose.yml` |
| 환경변수 (`POSTGRES_*`, `DB_*`, `API_KEY_PEPPER`, `RADA_POLICY_DIR`, `ML_SERVER_URL`, `RETRIEVAL_DISTANCE_MODE`) | 여러 곳 |
| Grafana datasource UID (`rada_pg`, `rada_spring`) | datasource yaml + 모든 dashboard JSON |

위 중 하나라도 변경해야 하면 **PR 디스크립션 1번째 줄에 명시 + 슬랙으로 전원 알림**.

---

## 6. 충돌 자주 발생하는 파일 + 해결

| 파일 | 충돌 위험 | 회피 전략 |
|---|---|---|
| `ml_server/config_yaml/scoring_policy.yaml` | **매우 높음** | 작은 PR 자주 머지. 큰 변경은 사전 슬랙. |
| `ml_server/scorer/signal_extractor.py` | 높음 | 기존 신호 안 건드리고 새 신호만 추가. |
| `ml_server/scorer/verdict_classifier.py` | 중 | 작은 변경 단위 PR. |
| `server-spring/.../dto/MlResponse.java` | 중 | 새 필드만 추가, 기존 변경 X. |
| `infra/grafana/provisioning/dashboards/rada-main.json` | **매우 높음** | 새 dashboard 파일에 본인 패널 분리. |
| `docker-compose.yml` | 중 | 전원 공유. |
| `application.yml`, `application-docker.yml` | 중 | 동일. |
| `requirements.txt`, `build.gradle` | 낮음 | 의존성 추가는 PR 에 이유 명시. |
| V*.sql 마이그레이션 | 중 | V 번호 사전 협의 (작업 시작 전 `git fetch upstream && ls server-spring/.../migration/` 확인). |

### 충돌 시나리오 — scoring_policy.yaml 동시 수정

```
A: cpu_high: 1 → 2
B: cpu_high: 1 → 0  (제거)
```

→ git merge 충돌. 둘이 슬랙 협의해서 결정자가 PR 본인 작업에서 해결.

**예방**: 작은 PR + 즉시 머지. yaml 큰 변경은 사전 알림.

### 충돌 시나리오 — rada-main.json 패널 동시 수정

→ JSON merge 가 거의 항상 어색. 권장: 본인 패널은 새 dashboard 파일에. 꼭 rada-main 손대야 하면 Grafana UI 에서 익스포트 다시.

### 충돌 시나리오 — V*.sql 마이그레이션 같은 번호 동시 추가

→ Flyway 가 충돌. 한쪽이 V+1 로 rename 하고 PR 갱신.

**예방**: 작업 시작 전 upstream 최신화 + 사용 중인 V 번호 확인.

---

## 7. PR 작성 가이드

PR 디스크립션 템플릿 (`.github/pull_request_template.md` 가 자동 로드):

```markdown
## 변경 요약
- (1~2줄)

## Contract 영향
- [ ] Flyway V*.sql 기존 파일 수정
- [ ] MetricsRequest 22-key 변경
- [ ] MlResponse / analyze_router 응답 형식 변경
- [ ] API 경로 변경
- [ ] ApiKeyHasher / 인증 알고리즘 변경
- [ ] anomaly_history.scores JSONB nested key 이름 변경
- [ ] 환경변수 / Docker service 이름 변경
- [ ] Grafana datasource UID 변경

(하나라도 체크 시: PR 디스크립션 최상단에 "★ ALL-TEAM SYNC 필요" 명시)

## 측정 / 검증
- Python tests: <N> passed
- Java tests: <N> passed
- (Grafana 변경 시) 스크린샷:
- (ML 변경 시) 본인 PC FP rate 측정:

## 비고
- (선택)
```

PR 크기: **가능한 작게**. 큰 변경은 여러 작은 PR 로 쪼개기. Reviewer 부담 + 충돌 최소화.

---

## 8. 디버깅 FAQ

### `python tools/anomaly_trigger.py` 가 401 Unauthorized

→ 시드 미적용. `docker cp infra/seed/demo_data.sql rada-postgres:/tmp/seed.sql && docker compose exec -T postgres sh -c "psql -U rada -d pc_monitor -f /tmp/seed.sql"` 실행.

→ 또는 `.env` 의 `API_KEY_PEPPER` 가 dev 기본값 (`dev_pepper_change_me`) 아님.

### Spring 컨테이너 unhealthy

```powershell
docker compose logs spring-server --tail 50
```

흔한 원인:
- Postgres 가 healthy 되기 전 Spring 부팅 → start_period 60초 내 회복
- Flyway 마이그레이션 checksum 충돌 → `application-docker.yml` 의 `rada.flyway.auto-repair: true` 자동 회복

### ML 컨테이너 unhealthy

```powershell
docker compose logs ml-server --tail 50
```

흔한 원인:
- `RADA_POLICY_DIR` 환경변수 오타
- scoring_policy.yaml / allowlist.yaml YAML 문법 오류 (본인이 yaml 수정 후 발생하면 yaml validator 점검)

### Grafana 패널 "No data"

- 시드 미적용 → 위 명령 재실행
- 데이터 시간대 밖 → 패널 윈도우 (`NOW() - INTERVAL '5 minutes'`) 확인
- search_path 이슈 → grafana 재시작 (`docker compose restart grafana`)

### Docker bind port 충돌 (Windows)

```
Error: bind: An attempt was made to access a socket in a way forbidden by its access permissions
```

Hyper-V/WSL 의 reserved port 영역 일시 점유. 확인:

```powershell
netsh int ipv4 show excludedportrange protocol=tcp
```

해결:
1. 시스템 재부팅 1회 (가장 빠름. reserved range 가 재할당됨)
2. 또는 docker-compose 의 호스트 매핑 변경 (영구적 PR — 다른 팀원 영향)

### git rebase 했더니 충돌

```powershell
git status                          # 충돌 파일 확인
notepad <충돌 파일>                   # <<< === >>> 마커 수동 해결
git add <해결 파일>
git rebase --continue

# 또는 전체 취소:
git rebase --abort
```

### 본인 PC 의 MAC 기반 PC_ID 확인

```powershell
python -c "from client_core.identity import PC_ID; print(PC_ID)"
```

본인 PC 로 client.py 돌리려면 이 ID 를 pc_info 에 등록해야 함. `tools/provision_pcs.py --input pcs.csv` 또는 직접 SQL.

### "한 번에 컨테이너 다 새로 짓고 싶음"

```powershell
docker compose down -v        # ★ -v 는 DB volume 도 삭제. 본인 PC 한정.
docker compose up -d --build
```

운영(NCP) 에는 절대 사용 금지.

---

## 9. 다음 큰 변경 — 카테고리 패턴 도입 (현재 v0.6.0 적용)

본 가이드 작성 시점에 카테고리 패턴 게이팅 (Resource/Network/System) 이 v0.6.0 로 도입됨.
관련 명세는 `docs/cryptojacking_detection_patterns.md` 의 31 패턴 카탈로그 참고.

**진행 중 또는 다가오는 변경**:
- 본인 PC 에서 4h+ 정상 traffic 수집 → FP rate 측정 (v0.5 → v0.6 비교)
- 카테고리 시각화 패널 (`rada-main.json` 또는 `rada-categories.json` 신규)
- 단계별 약화 4건의 점수 (`appdata_net`, `disk_write_net_out`, `unknown_proc_net`, `mining_pool_only`) 0 으로 삭제 검토

본인 영역이 위와 같은 파일 (`rada-main.json`, `scoring_policy.yaml`) 인 경우 **사전 슬랙 알림 + 작은 PR**.

---

## 10. 참고 문서

- [`README.md`](../README.md) — 프로젝트 개요, 빠른 시작
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — 일반 커밋 규칙
- [`docs/reference/docker-dev.md`](docker-dev.md) — dev 환경 상세
- [`docs/reference/cryptojacking_detection_patterns.md`](cryptojacking_detection_patterns.md) — mining 탐지 패턴 카탈로그
- [`docs/reference/pc-provisioning.md`](pc-provisioning.md) — PC 일괄 등록 도구
- [`docs/reference/retrieval_augmented_timeseries_manual.md`](retrieval_augmented_timeseries_manual.md) — retrieval 레이어 명세
- [`docs/reference/branch-protection.md`](branch-protection.md) — GitHub branch 보호 설정
- [`docs/reference/mcp-setup.md`](mcp-setup.md) — MCP 서버 설정 (선택)

---

## 11. 한 줄 요약

```
1. Fork upstream → clone fork → upstream remote 등록 → docker compose up → smoke
2. upstream main 동기화 → 작업 브랜치 → 작업 → 본인 fork push
3. 본인 fork → upstream PR → 템플릿 채워 제출
4. Contract surface (§5) 는 사전 협의
5. 본인 영역 (§4) 안에서 자유. 충돌 자주 발생 파일 (§6) 은 작은 PR 자주.
6. 테스트 통과 + 측정 결과 = PR 완료
7. 머지 후 본인 fork main 동기화 + 작업 브랜치 정리
```

질문은 GitHub Discussions 또는 슬랙.
