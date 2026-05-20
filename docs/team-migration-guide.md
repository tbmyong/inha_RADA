# RADA 팀 협업 & 마이그레이션 가이드

> 본 가이드는 RADA 프로젝트를 팀 단위로 평행하게 수정 → 머지하는 워크플로를 위한 것이다. 대시보드 담당자, ML 담당자, 또 다른 영역 담당자가 각자의 fork/branch 에서 작업하고 나중에 main 으로 통합할 때 충돌을 최소화하고 contract 를 깨뜨리지 않게 하는 방법을 정리한다.

**대상 독자**: RADA 를 처음 받아 자기 영역(대시보드, ML, 기타) 을 손보는 팀원.

**전제**: 본 repo 의 `CONTRIBUTING.md` 와 `docs/cryptojacking_detection_patterns.md` 를 미리 훑어봤다.

---

## 0. 5분 안에 셋업하고 첫 실행

```powershell
# 1) Repo clone
git clone https://github.com/Jjaerud/inha_RADA.git rada
cd rada

# 2) 환경 변수 (기본값 충분)
Copy-Item .env.example .env

# 3) Docker 4 컨테이너 빌드 + 기동
docker compose up -d --build

# 4) 정상 동작 검증 (모든 컨테이너 healthy 여야 함)
docker compose ps

# 5) 시드 데이터 + 스모크 트리거
type infra\seed\demo_data.sql | docker compose exec -T postgres psql -U rada -d pc_monitor
python tools\anomaly_trigger.py

# 6) Grafana 확인
start http://localhost:3000   # admin / admin
```

`docker compose ps` 에서 4 컨테이너 모두 `Up (healthy)` 인지 확인. 하나라도 unhealthy 면 `docker compose logs <서비스>` 으로 원인 추적.

---

## 1. 프로젝트 지도 — 어디가 뭘 하는가

```
rada/
├── client.py                          # 학생 PC 측 메트릭 수집 진입점 (얇은 shim)
├── client_core/                       # 수집/송신 로직 (모듈화)
│   ├── collector/                       cpu_mem/gpu/network/process/disk
│   ├── detector/                        local detector (boxplot, threshold)
│   ├── sender/                          ML/Spring 송신 + LocalQueue
│   ├── identity/                        PC_ID
│   ├── config/                          기본값 + env override
│   └── runtime/                         메인 루프
│
├── ml_server/                         # FastAPI ML 서버
│   ├── main.py                          앱 entry
│   ├── api/                             /analyze, /status, /admin, /history
│   ├── model/                           Pydantic 요청/응답 DTO
│   ├── detector/                        IsolationForest + LOF
│   ├── feature/                         10차원 feature 빌더
│   ├── scorer/                          ★ 점수/verdict 로직 (튜닝 영역)
│   ├── retrieval/                       segment / embedding / store / evidence
│   ├── policy/                          YAML 로더
│   ├── config_yaml/                     ★ scoring_policy.yaml / allowlist.yaml
│   ├── agent/                           Claude API agent + mock fallback
│   ├── storage/                         pc_history_store
│   ├── scheduler/                       재학습 스케줄러
│   └── silent_fail_counters.py          /status 에 노출되는 카운터
│
├── server-spring/                     # Spring Boot 수신 서버
│   ├── src/main/java/com/lab/monitor/
│   │   ├── controller/                  /api/metrics 등 API
│   │   ├── service/                     수집/저장/ML 포워딩/알람
│   │   ├── dto/                         ★ MetricsRequest / MlResponse
│   │   ├── entity/                      JPA 엔티티
│   │   ├── security/                    API key 해시/필터
│   │   └── config/                      WebClient/Async/Flyway
│   └── src/main/resources/
│       ├── application.yml              운영 기본 프로파일
│       ├── application-docker.yml       dev 프로파일
│       └── db/migration/V*.sql          ★ Flyway 마이그레이션
│
├── infra/
│   ├── grafana/
│   │   ├── grafana.ini
│   │   └── provisioning/
│   │       ├── datasources/             ★ datasource UID 매핑
│   │       └── dashboards/              ★ 패널 JSON
│   ├── ncp/                             운영(NCP) systemd / 스크립트
│   └── seed/                            데모 시드 SQL
│
├── tools/                             # 일회용 / 운영 도구
│   ├── anomaly_trigger.py               mining 시나리오 인젝션
│   ├── provision_pcs.py                 PC 일괄 등록
│   ├── retrieval_realdata_eval.py       retrieval 품질 측정
│   └── ...
│
├── tests/                             # Python 테스트 (282+)
├── docs/                              # 본 가이드 등 문서
├── docker-compose.yml                 ★ 컴포넌트 4개 정의
├── .env.example                       환경변수 템플릿
└── README.md
```

`★` 표시된 곳이 **자주 수정되는 hotspots** — 충돌 가능성이 큰 영역.

---

## 2. 역할별 워크플로

### 2-A. 대시보드 담당자

#### 자유롭게 손대도 되는 곳

| 파일 | 설명 |
|---|---|
| `infra/grafana/provisioning/dashboards/*.json` | 패널 추가/삭제/SQL 수정/색감/레이아웃 모두 자유 |
| `infra/grafana/grafana.ini` | Grafana 자체 설정 (조심) |
| `docs/dashboard-*.md` (신규) | 본인 작업 문서 |

#### 절대 손대지 말 것

- `infra/grafana/provisioning/datasources/postgres.yaml` 의 `uid: rada_pg`
- `infra/grafana/provisioning-docker/datasources/*.yaml` 의 `uid`
- 다른 사람의 패널 (가능하면 신규 dashboard 파일을 만들기)

#### 동시 작업 안전 전략

- 동일 dashboard JSON 을 여러 명이 수정하면 **JSON merge 가 거의 항상 충돌**. 권장:
  - 새 dashboard 가 필요하면 **새 파일** 로 만들 것 (예: `rada-team-A.json`)
  - rada-main.json 이나 rada-pc-detail.json 은 가능한 한 안 건드림
  - 꼭 건드려야 하면 main 브랜치에 작은 변경 단위로 빠르게 머지

#### PR 전 체크리스트

- [ ] 변경한 JSON 이 Grafana 에 정상 로드되는지 확인 (`docker compose restart grafana` 후 패널 열어보기)
- [ ] datasource UID `rada_pg` / `rada_spring` 만 사용 (다른 UID 만들지 말 것)
- [ ] 패널 query 의 컬럼명이 `pc_monitor.metrics_history` 등 실제 스키마와 일치
- [ ] 신규 패널은 PR 에 **스크린샷 포함** (리뷰 도움)

### 2-B. ML / 점수 담당자

#### 자유롭게 손대도 되는 곳

| 파일/디렉토리 | 설명 |
|---|---|
| `ml_server/scorer/signal_extractor.py` | ★ 신호 추출 로직 (가장 핫한 튜닝 포인트) |
| `ml_server/scorer/indicator_calculator.py` | 신호 → 점수 계산 |
| `ml_server/scorer/verdict_classifier.py` | 점수 → verdict |
| `ml_server/scorer/context_multiplier.py` | context discount |
| `ml_server/detector/anomaly_predictor.py` | IF/LOF 파라미터 |
| `ml_server/feature/feature_builder.py` | 10차원 feature 추출 |
| `ml_server/retrieval/segment_embedding.py` | embedding 함수 |
| `ml_server/retrieval/retrieval_store.py` | distance 함수, top-k 검색 |
| `ml_server/retrieval/retrieval_evidence.py` | evidence 빌더 |
| **`ml_server/config_yaml/scoring_policy.yaml`** | ★ 임계값 / 점수 / 게이팅 |
| **`ml_server/config_yaml/allowlist.yaml`** | 허용 프로세스 |

#### 절대 손대지 말 것

- `ml_server/model/requests.py` 의 기존 22-key 필드 이름/타입
- `ml_server/api/analyze_router.py` 응답의 **기존 top-level 키 이름** (`overall_severity`, `verdict`, `scores`, `score_breakdown` 9키, `alerts`, `retrieval_evidence`, `signals_missing`, `policy_version`)
- `scoring_policy.yaml` 의 `version` (변경 시 호환 표시 — 보정 시 `scoring-v0.X.Y` 형식 유지)

#### 동시 작업 안전 전략

- **`scoring_policy.yaml` 동시 수정은 거의 항상 충돌** — 다음 중 하나:
  - PR 작게, 자주, 빠르게 머지
  - 또는 변경 사유별로 다른 yaml 으로 분리 (예: `scoring_policy_v0.6.yaml`) — 단 로더 수정 필요
- 신호/점수 추가만 하고 기존 신호 점수/이름은 안 건드리는 게 충돌 회피에 가장 효과적
- `verdict_classifier.py` 같은 핫 파일은 작은 변경 단위로 PR

#### PR 전 체크리스트

- [ ] `python -m pytest --tb=line -q` 로컬 통과 (CI 가 잡지만 미리)
- [ ] `python tools/anomaly_trigger.py` → anomaly_history 에 HIGH 신규 row 들어가는지 확인
- [ ] 본인 PC 정상 사용 데이터 (4h 권장) 로 FP rate 측정 → PR description 에 첨부
- [ ] `scoring_policy.yaml` 변경 시 `version` 도 올림 (예: `scoring-v0.5.0` → `scoring-v0.5.1`)

### 2-C. 클라이언트 / 데이터 수집 담당자

#### 자유롭게 손대도 되는 곳

| 파일/디렉토리 | 설명 |
|---|---|
| `client_core/collector/*` | 수집 로직 내부 (단, 출력 키 셋 보존) |
| `client_core/detector/*` | 로컬 탐지기 |
| `client_core/sender/*` | 송신 로직 |
| `client_core/identity/*` | PC ID 로직 |
| `client_core/runtime/*` | 메인 루프 |

#### 절대 손대지 말 것

- `client_core/model/payload.py` 의 `ML_PAYLOAD_KEYS` 22개 키 이름
- `client.py` shim 의 legacy 함수 시그니처

#### PR 전 체크리스트

- [ ] `python -m pytest tests/unit/test_orchestrator_derived.py` → derived_features 키 개수 변경 없음 확인 (또는 의도된 추가)
- [ ] 본인 PC 에서 `python client.py` 5분 돌려서 metric 정상 송신 확인

### 2-D. 인프라 / 운영 담당자

#### 자유롭게 손대도 되는 곳

| 파일/디렉토리 | 설명 |
|---|---|
| `infra/ncp/scripts/*` | 운영 설치 스크립트 |
| `infra/ncp/systemd/*` | systemd 유닛 |
| `infra/ncp/README.md` | 운영 문서 |
| `tools/*` | 운영 도구 |

#### 절대 손대지 말 것

- `docker-compose.yml` 의 service 이름 (`postgres`, `ml-server`, `spring-server`, `grafana`) — 다른 컴포넌트가 hostname 으로 참조
- `Dockerfile` 의 expose port 번호 (8000, 8080, 8081 internal, 3000, 5432)

---

## 3. Contract 절대선 (모두 공통)

본 항목들은 **한 명이 바꾸면 모두에게 영향**. 변경 시 반드시 사전 협의 + 전원 동의:

| Contract 영역 | 위치 |
|---|---|
| 22-key Agent payload | `client_core/model/payload.py` + `server-spring/.../MetricsRequest.java` + `ml_server/model/requests.py` 3 파일 동시 |
| ML 응답 형식 (top-level keys) | `ml_server/api/analyze_router.py` + `server-spring/.../MlResponse.java` |
| score_breakdown 9 키 | `ml_server/scorer/verdict_classifier.py` + Grafana dashboard SQL |
| `anomaly_history.scores` JSONB nested keys (`retrieval_evidence`, `signals_missing`, `policy_version`) | `ml_server/api/analyze_router.py` + `server-spring/.../AlertService.java` + Grafana SQL |
| API 경로 (`/api/metrics`, `/analyze`, `/actuator/health`, `/actuator/prometheus`, `/status`, `/admin/*`, `/history/{pc_id}`) | controller/router 코드 |
| 인증 알고리즘 `SHA-256(pepper + ":" + raw_key)` | `ApiKeyHasher.java` + `tools/provision_pcs.py` |
| Flyway 기존 V*.sql 파일 (V1~V8) | `server-spring/.../db/migration/` |
| Docker compose service 이름 | `docker-compose.yml` |
| 환경변수 이름 (`POSTGRES_*`, `DB_*`, `API_KEY_PEPPER`, `RADA_POLICY_DIR`, `GRAFANA_DB_*`, `ML_SERVER_URL`, `RETRIEVAL_DISTANCE_MODE`, `RETRIEVAL_NORMALIZE`) | 여러 곳 |
| Grafana datasource UID (`rada_pg`, `rada_spring`) | datasource yaml + 모든 dashboard JSON |

본인 영역에서 위를 건드려야 하면 **무조건 PR 디스크립션에 명시 + 전원 리뷰 1 회 이상 요청**.

---

## 4. Branch 전략 + 명명 규칙

```
main                                ← 보호 (직접 push 금지)
 ├── feat/scoring-tighten-fp        ← 본인 작업 브랜치
 ├── feat/dashboard-pc-detail-v2
 ├── fix/grafana-piechart-color
 ├── docs/contributor-guide
 └── ...
```

### Conventional Commits

```
feat(scope): 새 기능
fix(scope): 버그 수정
docs(scope): 문서만
refactor(scope): 동작 변경 없는 리팩터링
test(scope): 테스트 추가/수정
chore(scope): 빌드/CI/의존성/포맷

scope 예시: client / spring / ml / grafana / ops / docs / tools
```

### 브랜치 명명

- `feat/<짧은-설명>` — 신규 기능
- `fix/<짧은-설명>` — 버그
- `docs/<짧은-설명>` — 문서
- `chore/<짧은-설명>` — 잡일

### PR 머지

- Squash merge 권장 (history 깔끔)
- main 에 force push 금지

---

## 5. 충돌 회피 전략 — 동시 작업 가능 vs 조율 필요

### 동시 작업 안전 (서로 영향 없음)

- 본인이 새로 만든 파일 (신규 dashboard JSON, 새 detector module, 새 test)
- 본인 영역의 isolated 모듈 (예: ML 담당 `retrieval/embedding.py` 와 Dashboard 담당 `rada-main.json` 동시 작업)
- 본인 영역의 README / 문서

### 조율 필요 (충돌 가능 高)

| 파일 | 조율 방법 |
|---|---|
| `ml_server/config_yaml/scoring_policy.yaml` | 동시 수정 거의 항상 충돌. **작게/자주 PR**, 또는 사전 슬랙으로 알리고 작업 |
| `ml_server/scorer/signal_extractor.py` | 신호 추가만 하고 기존 안 건드리면 충돌 적음 |
| `ml_server/scorer/verdict_classifier.py` | 동시 수정 위험. PR 작게 |
| `server-spring/.../MlResponse.java` | contract 라 수정 자체 자제 |
| `infra/grafana/provisioning/dashboards/rada-main.json` | 가능한 한 새 파일에 추가, rada-main 직접 수정 자제 |
| `docker-compose.yml` | 변경 시 전원 공유 |
| `application.yml`, `application-docker.yml` | 동일 |
| `requirements.txt`, `build.gradle` | 의존성 추가는 PR 디스크립션에 이유 명시 |

### 작업 시작 전 체크

```powershell
# main 의 최신 가져오기
git checkout main
git pull origin main

# 본인 브랜치 생성
git checkout -b feat/my-work

# 또는 기존 본인 브랜치를 main 에 맞춰 rebase
git checkout feat/my-work
git rebase origin/main
```

이걸 안 하고 옛 main 위에서 작업하면 PR 시 충돌 폭주.

---

## 6. 자주 발생하는 충돌 시나리오 + 해결

### 시나리오 A: scoring_policy.yaml 동시 수정

```
A 사람: cpu_high: 1 → 2 변경
B 사람: cpu_high: 1 → 0 변경  (제거)
```

→ git merge 충돌. 둘 중 누구를 채택할지 슬랙 협의. 결정자가 PR 본인이 가서 해결.

**예방**: 작은 변경마다 PR + 즉시 merge. 큰 변경은 사전 공유.

### 시나리오 B: rada-main.json 같은 dashboard 동시 수정

```
A 사람: panel id=10 위치 변경
B 사람: panel id=15 신규 추가
```

→ JSON merge 가 거의 항상 어색하게 됨. JSON 의 structural diff 가 어려움.

**해결**: 한 명의 변경을 먼저 머지 → 다른 사람이 rebase 후 본인 변경 reapply (Grafana UI 에서 다시 익스포트 하는 게 가장 안전).

**예방**: 가능한 한 새 dashboard 파일 만들기.

### 시나리오 C: V*.sql 마이그레이션 동시 추가

```
A 사람: V9__add_my_column.sql 추가
B 사람: V9__add_other_column.sql 추가  (같은 V9!)
```

→ Flyway 가 둘 중 하나만 실행하거나 충돌 에러.

**해결**: 한쪽이 V10 으로 rename. 머지 순서 협의.

**예방**: V 번호 사전 슬랙 협의. `git fetch && git log --all --oneline -- 'server-spring/src/main/resources/db/migration/*'` 로 사용된 V 확인.

### 시나리오 D: MlResponse.java / Pydantic 응답 추가 필드

```
A 사람: MlResponse 에 newFieldX 추가
B 사람: MlResponse 에 newFieldY 추가
```

→ 충돌 발생 가능하나 의미적 의존 없으면 머지 쉬움.

**예방**: 응답 형식 추가는 사전 전원 합의. PR 디스크립션에 "응답 키 추가" 명시.

### 시나리오 E: 두 명이 같은 docker-compose 서비스 수정

→ 안 됨. docker-compose.yml 은 인프라 담당 또는 합의된 한 명만 수정.

---

## 7. PR 워크플로

### 7-1. PR 생성 전

```powershell
# 1) main 최신화
git checkout main
git pull origin main

# 2) 본인 브랜치 rebase
git checkout feat/my-work
git rebase origin/main
# 충돌 있으면 해결 + git rebase --continue

# 3) 로컬 테스트
python -m pytest --tb=line -q       # 282+ passed 기대
cd server-spring
.\gradlew test --tests "*Test"      # 단위 67+ passed 기대
cd ..

# 4) Docker compose 빌드 검증 (필요 시)
docker compose up -d --build
docker compose ps                    # 모두 healthy 여야 함
```

### 7-2. PR 제출

- 제목: Conventional Commits 형식 (예: `feat(ml): add user_idle_ms collection`)
- 디스크립션: PR 템플릿 채우기 (`.github/pull_request_template.md` 자동 로드)
- Contract 영향 체크리스트에 정직하게 체크
- 변경 사유 1~2 줄
- 테스트 결과 (회귀 0 / 신규 N 추가)
- (선택) Grafana 패널 변경 시 스크린샷

### 7-3. 리뷰 + 머지

- 최소 1 review 받은 후 squash merge
- main 에 직접 push 금지 (branch protection)

---

## 8. 처음 가져다 쓰기 — 단계별

처음 RADA 를 받아 본인 PC 에서 돌려보고 본인 영역 작업 시작까지:

### 8-1. 환경 점검

| 요구 | 권장 버전 |
|---|---|
| Git | ≥ 2.30 |
| Python | 3.11 |
| Java | 17 (JDK) |
| Docker Desktop (Windows) | ≥ 4.0 with WSL2 |
| Node.js (선택, MCP 사용 시) | LTS |

```powershell
git --version
python --version
java -version
docker --version
node --version       # 선택
```

### 8-2. Clone + 환경 셋업

```powershell
git clone https://github.com/Jjaerud/inha_RADA.git rada
cd rada
Copy-Item .env.example .env
```

`.env` 확인 — 기본값으로 dev 충분. `API_KEY_PEPPER` 가 `dev_pepper_change_me` 인 것은 시드 해시와 매칭됨. 변경하면 시드 인증 깨짐 (운영 배포 전엔 안 건드림 권장).

### 8-3. Python 의존성

```powershell
pip install -r requirements.txt
# 또는 venv 사용:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 8-4. Docker 컨테이너

```powershell
docker compose up -d --build
# 첫 빌드 5~10분 소요 (Spring multi-stage + ML 의존성)

docker compose ps
# 4 컨테이너 모두 (postgres, ml-server, spring-server, grafana) Up (healthy) 확인
```

### 8-5. 시드 + 스모크 테스트

```powershell
type infra\seed\demo_data.sql | docker compose exec -T postgres psql -U rada -d pc_monitor
# 출력: INSERT 0 40, INSERT 0 2400 등

python tools\anomaly_trigger.py
# 15/15 OK 나와야 정상
```

### 8-6. Grafana

```powershell
start http://localhost:3000
# admin / admin → 첫 로그인 시 비밀번호 변경 프롬프트 (skip 가능)
# Dashboards → RADA → rada-main / rada-pc-detail
```

### 8-7. 본인 영역 작업

```powershell
git checkout -b feat/my-work
# 코드 수정...
git add <변경 파일>
git commit -m "feat(scope): 한 줄 설명"
git push -u origin feat/my-work
# GitHub 에서 PR 생성
```

---

## 9. 디버깅 / 문제 해결 FAQ

### "anomaly_trigger 가 401 unauthorized"

→ 시드 미적용. `type infra\seed\demo_data.sql | docker compose exec -T postgres psql -U rada -d pc_monitor` 실행.

→ 또는 pepper 가 dev 기본값 (`dev_pepper_change_me`) 이 아님. `.env` 의 `API_KEY_PEPPER` 확인.

### "anomaly_trigger 가 500 internal server error + timestamp 오류"

→ 본인 timezone 설정 이상. `client.py` 가 만드는 timestamp 가 timezone offset 없으면 Spring 이 reject. 최신 main 인지 확인 (645729c 커밋 이후 fix).

### "Grafana 패널이 No data"

→ 시드 미적용 또는 데이터 시간대 밖. 시드 다시 적용 + `python tools/anomaly_trigger.py` 로 fresh 데이터 생성. 패널 윈도우 확인 (`NOW() - INTERVAL '5 minutes'` 등).

### "Spring 컨테이너가 unhealthy"

```powershell
docker compose logs spring-server --tail 50
```

흔한 원인:
- Postgres 가 healthy 되기 전 Spring 부팅 → start_period 60초 안에 회복 (그래도 unhealthy 면 재시작)
- Flyway 마이그레이션 충돌 (V*.sql 의 checksum 변경) → `application-docker.yml` 의 `rada.flyway.auto-repair: true` 로 자동 회복

### "ML 컨테이너가 unhealthy"

```powershell
docker compose logs ml-server --tail 50
```

흔한 원인:
- `RADA_POLICY_DIR` 환경변수 오타 → docker-compose.yml 의 ml-server 환경변수 확인
- scoring_policy.yaml / allowlist.yaml 문법 오류 → 본인이 yaml 수정했으면 yaml validator 로 점검

### "내 PC ID 가 모르겠음"

```powershell
python -c "from client_core.identity import PC_ID; print(PC_ID)"
```

본인 PC 의 MAC 기반 ID. 이걸 pc_info 에 등록해야 client.py 가 자기 키로 인증 가능.

### "한 번에 컨테이너 다 새로 짓고 싶음"

```powershell
docker compose down -v        # ★ 주의: -v 는 볼륨도 삭제 (DB 데이터 다 날아감)
docker compose up -d --build
```

dev 환경 한정. 운영 (NCP) 에서는 절대 `-v` 쓰지 말 것.

### "git rebase 했더니 충돌"

```powershell
# 한 파일씩 충돌 해결
git status                    # 충돌 파일 확인
notepad <충돌 파일>             # <<< === >>> 마커 해결
git add <해결한 파일>
git rebase --continue

# 또는 전체 취소
git rebase --abort
```

---

## 10. 마이그레이션 시나리오 — 본인 작업을 main 에 통합

### 케이스 A: ML 담당이 점수 정책 + 신호 추가했음

```powershell
# 1) 본인 브랜치 main 에 맞춰 최신화
git checkout feat/scoring-tighten
git rebase origin/main

# 2) 회귀 테스트
python -m pytest --tb=line -q
# 282 + 본인 추가 N개 통과 확인

# 3) 본인 PC 데이터 + anomaly_trigger 로 효과 측정
python tools/anomaly_trigger.py
# anomaly_history 확인 → 새 점수 정책으로 HIGH 잡히는지

# 4) PR
git push -u origin feat/scoring-tighten
# GitHub UI 에서 PR 생성 + 본인 측정 결과 첨부
```

PR 디스크립션 예시:
```
## 변경 요약
- scoring_policy.yaml 의 appdata_net: 6 → 2 약화
- 새 신호 cpu_gpu_sustained_flat 도입 (v0.6.0)

## Contract 영향
- [x] scoring_policy.yaml version 변경 (v0.5.0 → v0.6.0)
- [ ] 응답 형식 변경 없음
- [ ] DB 스키마 변경 없음

## 측정
- 본인 PC 4h 정상 데이터 FP rate: 18.2% → 2.1%
- anomaly_trigger mining 15회: HIGH 15/15 유지

## 테스트
- Python 282 + 신규 8 = 290 passed
```

### 케이스 B: 대시보드 담당이 새 패널 추가

```powershell
# 1) 본인 브랜치 main 에 맞춰
git checkout feat/dashboard-mining-trend
git rebase origin/main

# 2) Grafana 컨테이너 재시작해서 변경 반영 확인
docker compose restart grafana
start http://localhost:3000     # 새 패널 정상 표시 확인

# 3) PR
git push -u origin feat/dashboard-mining-trend
```

PR 디스크립션 예시:
```
## 변경 요약
- rada-main.json 에 "최근 24h Mining suspect timeline" 패널 추가 (panel id=50)

## Contract 영향
- [x] datasource UID `rada_pg` 사용 (변경 없음)
- [x] anomaly_history.scores->>'final' 컬럼 사용 (스키마 변경 없음)

## 측정
- 스크린샷 첨부
- 패널 SQL 의 응답 시간: 80ms (mining 시연 데이터 기준)
```

### 케이스 C: 클라이언트 담당이 신규 derived feature 추가

```powershell
# 1) ML 담당과 사전 협의 — ML 도 이 feature 받아야 의미 있음
# 2) 본인 작업
git checkout -b feat/client-add-process-tree-depth

# 3) 통신 호환 확인
# - payload.py 의 OPTIONAL_PAYLOAD_KEYS 에 추가 (필수 X)
# - ML 서버는 Pydantic 의 free-form 으로 받음

# 4) 테스트
python -m pytest tests/unit/test_orchestrator_derived.py -q

# 5) PR — ML 담당이 후속 PR 로 feature 활용 코드 추가
```

---

## 11. 머지 후 본인이 할 것

```powershell
# main 동기화
git checkout main
git pull origin main

# 본인 브랜치 정리
git branch -d feat/my-work       # 로컬 삭제
git push origin --delete feat/my-work    # 원격도 삭제 (선택)
```

PR 머지 후 main 에서 본인 변경이 동작하는지 한번 더 확인:

```powershell
docker compose up -d --build
docker compose ps
python -m pytest --tb=line -q
```

---

## 12. 한 줄 요약

```
1. Clone → .env 복사 → docker compose up → smoke 통과 = 환경 준비
2. main 최신화 → 본인 feat/ 브랜치 → 작업 → PR 템플릿 채워 제출
3. Contract surface 는 안 건드리거나 사전 협의
4. 본인 영역 (Resource/Network/System pattern, scorer, dashboard) 은 자유롭게
5. 테스트 통과 + 본인 PC 측정 첨부 = PR 완료
```

문서가 답 안 주는 게 있으면 슬랙 또는 GitHub Discussions 에 질문.

---

## 13. 참고 문서

- [`README.md`](../README.md) — 프로젝트 개요 + 빠른 시작
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — branch 전략 + 커밋 규칙 (일반)
- [`docs/docker-dev.md`](docker-dev.md) — dev 환경 상세
- [`docs/cryptojacking_detection_patterns.md`](cryptojacking_detection_patterns.md) — 탐지 패턴 reference
- [`docs/pc-provisioning.md`](pc-provisioning.md) — PC 일괄 등록
- [`docs/retrieval_augmented_timeseries_manual.md`](retrieval_augmented_timeseries_manual.md) — retrieval 레이어 명세
- [`docs/branch-protection.md`](branch-protection.md) — GitHub branch 보호 설정

문서들이 빠진 정보가 있으면 PR 로 보완하기.
