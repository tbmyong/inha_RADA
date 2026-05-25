# GitHub Repo 셋업 — 작업 시작 전

> **시작점**. 본인 PC 에 코드를 가져오고 환경변수까지 준비하는 단계.
> 이 단계가 끝나면 [`ncp_deployment.md`](ncp_deployment.md) 로 진행.

## 작업 순서 (이 문서의 흐름)

```
1. Repo 구조 이해 — 무엇이 들어있고 무엇이 빠져있는지
2. Fork (개인 작업) 또는 Clone (운영)
3. 본인 PC 에 .env 만들기
4. (선택) 로컬 docker compose 로 동작 검증
5. 다음 단계 → NCP 배포
```

---

## 1. Repo 구조 — 핵심만

```
inha_RADA/
├── client.py                       클라이언트 entry (PyInstaller 빌드 대상)
├── client_core/                    수집/탐지/전송 로직 (Python 패키지)
├── ml_server/                      FastAPI ML 서버 (scoring v0.8.0)
│   └── config_yaml/                scoring_policy.yaml + allowlist.yaml
├── server-spring/                  Spring Boot 메인 API (Flyway V1~V8)
│   └── src/main/resources/db/migration/   ← 스키마 정의
├── infra/
│   ├── grafana/                    대시보드 + 데이터소스 provisioning
│   ├── seed/                       데모 시드 (dev 전용)
│   └── ncp/                        (legacy systemd 자료 — 현재 운영엔 미사용)
├── tools/
│   ├── provision_pcs.py            API key 발급/회전
│   ├── anomaly_trigger.py          mining 시나리오 검증
│   └── stealth_trigger.py          fast-path 회피 검증
├── tests/                          pytest 79 케이스
├── docker-compose.yml              로컬 dev (postgres 포함)
├── .env.example                    환경변수 템플릿 (실제 .env 는 gitignore)
└── docs/                           본 문서 포함 모든 가이드
```

### Repo 에 **있는 것**

- 모든 소스 코드
- Flyway migration SQL (DB 스키마)
- Grafana 대시보드 JSON
- ML scoring policy YAML
- 빌드 / 테스트 / Docker 설정
- 모든 docs

### Repo 에 **없는 것** (반드시 별도 준비)

| 항목 | 어디서 만드나 | 왜 없나 |
|---|---|---|
| `.env` | `.env.example` 복사 후 값 채움 | 비밀번호 / API key 평문 포함, 절대 commit 금지 |
| `dist/rada_client.exe` | `pyinstaller ...` 빌드 산출물 | 22MB 바이너리, 빌드 환경에 따라 다름 |
| `keys.csv` | `tools/provision_pcs.py` 실행 결과 | 학생 PC raw_key 평문 — 보안 |
| `docker-compose.ncp.yml` | NCP VM 에서 `docker-compose.yml` 복사 후 수정 | 운영 전용 변형 (postgres 컨테이너 제외) |
| NCP `.env` | NCP VM `/opt/rada/.env` 별도 작성 | 운영 자격증명 |

> `.gitignore` 에 `.env`, `dist/`, `keys.csv`, `*.spec` 모두 명시되어 있음. 실수로 commit 안 되게 보호.

---

## 2. Fork (개인 작업용)

팀원이 본인 fork 에서 작업하고 PR 로 main 에 합치는 흐름. 자세한 절차는 [`team-guide.md`](team-guide.md).

빠른 시작:

1. GitHub 에서 `Jjaerud/inha_RADA` 의 우상단 **Fork** 클릭
2. 본인 계정의 fork 로 이동
3. 로컬에 clone:

```powershell
cd C:\Users\admin\Desktop
git clone https://github.com/<본인>/inha_RADA.git rada
cd rada
```

4. upstream 추가 (원본 변경사항 받아오기 위함):

```powershell
git remote add upstream https://github.com/Jjaerud/inha_RADA.git
git remote -v
```

→ 4줄 (origin / upstream 각각 fetch + push) 보이면 정상.

## 2-B. 직접 Clone (운영 / 단일 작업자)

Fork 없이 main repo 직접 작업:

```powershell
cd C:\Users\admin\Desktop
git clone https://github.com/Jjaerud/inha_RADA.git rada
cd rada
```

---

## 3. 본인 PC `.env` 작성 (로컬 dev 용)

```powershell
Copy-Item .env.example .env
notepad .env
```

기본값으로도 로컬 dev 는 충분 (모두 `dev_` 시작). 수정할 필요 거의 없음. **운영 (NCP) 용 `.env` 는 별개** — NCP VM 에서 다시 작성 (다음 문서).

### `.env.example` 내용 한눈에

```
POSTGRES_DB=pc_monitor
POSTGRES_USER=rada
POSTGRES_PASSWORD=rada_dev_pw       ← 로컬 dev 비밀번호
DB_SCHEMA=pc_monitor

API_KEY_PEPPER=dev_pepper_change_me  ← 운영선 강한 무작위 hex
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin     ← 운영선 강한 무작위
GRAFANA_DB_USER=rada
GRAFANA_DB_PASSWORD=rada_dev_pw

# MCP 서버 (선택 — Claude Code MCP 사용 시)
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
GRAFANA_URL=http://localhost:3000
GRAFANA_API_KEY=glsa_...
```

---

## 4. (선택) 로컬 docker compose 로 검증

NCP 배포 전에 로컬에서 한 번 돌려보면 디버그 편함:

```powershell
docker compose up -d --build
docker compose ps
```

3 ~ 5분 대기. 4개 컨테이너 (`rada-postgres`, `rada-ml`, `rada-spring`, `rada-grafana`) 모두 `Up` 또는 `healthy` 떠야 정상.

검증:

```powershell
# Spring 헬스 (컨테이너 내부)
docker exec rada-spring curl -fsS http://localhost:8081/actuator/health
# → {"status":"UP"}

# Grafana 접속
start http://localhost:3000
# admin / admin (.env 기본값) — 첫 로그인 후 즉시 변경 요구
```

데모 시드 + mining 트리거:

```powershell
Get-Content infra\seed\demo_data.sql -Raw `
  | docker compose exec -T postgres psql -U rada -d pc_monitor

python tools\anomaly_trigger.py     # fast-path
python tools\stealth_trigger.py     # behavior-only
```

`anomaly_history` 테이블에 HIGH_RISK 행이 누적되면 성공.

정지:
```powershell
docker compose down       # 컨테이너만 정지 (데이터 유지)
docker compose down -v    # 데이터까지 삭제
```

---

## 5. 작업 흐름 일반

### 코드 변경 → 반영

```powershell
# 본인 PC 에서 작업
git checkout -b feature/<짧은-설명>
# ... 코드 수정 ...
git add <변경 파일>
git commit -m "<설명>"
git push origin feature/<짧은-설명>

# GitHub 에서 PR 생성 → 리뷰 → main 머지
```

### NCP 운영 환경에 변경 반영

main 머지 후 [`deploy_updates.md`](deploy_updates.md) 절차로 NCP VM 에 pull + 재빌드.

### 운영 변경 영향 범위 한눈에

| 변경 | NCP 재빌드? | 학생 PC 재배포? |
|---|---|---|
| 클라이언트 코드 (`client_core/`, `client.py`) | ❌ | ✅ exe 재빌드 + 학생 PC 배포 |
| ML 서버 코드 / scoring yaml | ✅ `up -d --build ml-server` | ❌ |
| Spring 코드 / Flyway migration | ✅ `up -d --build spring-server` | ❌ |
| Grafana dashboard JSON | ❌ `restart grafana` | ❌ |
| 페이로드 22 키 형식 변경 | ✅ 양쪽 다 | ✅ |

---

## 자주 부딪힌 함정 — 이 단계에서

| 함정 | 증상 | 해결 |
|---|---|---|
| `.env` 가 없음 | docker compose 가 default 값으로 뜨거나 에러 | `Copy-Item .env.example .env` 먼저 |
| 8080 포트 점유 | Spring 컨테이너 시작 실패 | 다른 프로그램 정지 또는 `docker-compose.yml` 포트 변경 |
| Windows Hyper-V 가 5432 예약 | postgres 컨테이너 바인드 실패 | 본 repo 는 이미 `25432:5432` 매핑으로 회피 |
| Docker Desktop 미실행 | `docker compose up` 실행 안 됨 | Docker Desktop 먼저 실행 |
| 한글 cmd 깨짐 | PowerShell 결과 한글이 `?` | 무관 (파일 내용은 정상). 다음 SSH 세션 등에선 정상 |

---

## 다음 단계

본인 PC 에 코드 + .env 준비 완료 → **NCP 서버 셋업**:

→ [`ncp_deployment.md`](ncp_deployment.md)

## 참고 문서

- [`team-guide.md`](team-guide.md) — Fork 워크플로우 자세히
- [`branch-protection.md`](branch-protection.md) — main 브랜치 보호 정책
- [`docker-dev.md`](docker-dev.md) — 로컬 docker dev 상세
- [`deploy_updates.md`](deploy_updates.md) — 운영 변경사항 배포
