# NCP 서버 셋업 — 실전 가이드

> **이전 단계**: [`github_setup.md`](github_setup.md) (코드 + .env 준비됨)
> **다음 단계**: [`client_deployment.md`](client_deployment.md) (학생 PC 배포)

NCP 계정만 있는 백지 상태부터 RADA 서버 (Docker compose + Cloud DB managed) 가 동작할 때까지. **실제 셋업 시 부딪힌 모든 함정과 우회 방법** 포함.

## 작업 순서 (이 문서의 흐름)

```
Phase 1   NCP 콘솔 작업 (네트워크 + DB + VM)        ~30분
Phase 2   App VM SSH 셋업 (Docker + 코드 + .env)    ~20분
Phase 3   Docker Compose NCP 모드 + Flyway          ~10분
Phase 4   외부 접속 검증 + ACG 마무리                ~10분
Phase 5   Retention crontab + 운영 안정화           ~5분
```

총 약 1시간 15분.

---

## Phase 1 — NCP 콘솔 작업

### 1-1. Region / Platform

- 콘솔: <https://console.ncloud.com>
- 좌상단 **Region: KR** (가까움)
- 좌상단 **Platform: VPC** (Classic 아님 주의)

### 1-2. VPC + Subnet

**VPC 생성**: Services → Networking → VPC → 생성

| 항목 | 값 |
|---|---|
| 이름 | `rada-vpc` |
| IPv4 CIDR | `10.0.0.0/16` |

**Subnet 2개**: VPC → Subnet 관리 → 생성

| 이름 | CIDR | Type | 용도 | 비고 |
|---|---|---|---|---|
| `rada-app-sn` | `10.0.1.0/24` | **Public** | **일반** | App VM 용 |
| `rada-db-sn` | `10.0.2.0/24` | **Private** | **일반** | Cloud DB 용 |

> ⚠ **함정 — 용도 옵션 4개** (일반 / Baremetal / 로드밸런서 / NATGateway)
> → 둘 다 **"일반"** 선택. "일반/Baremetal/LB/NAT" 와 "Public/Private" 는 **별개 축**, 둘 다 정해야 함.
> → 만들고 나면 변경 불가, 잘못 만들면 삭제 후 재생성.

### 1-3. Cloud DB for PostgreSQL 생성

Services → Database → Cloud DB for PostgreSQL → DB Server 생성

| 항목 | 값 | 메모 |
|---|---|---|
| DB Engine | **PostgreSQL 15.15** | NCP 최신 15.x. RADA 는 15/16 둘 다 호환 |
| DB Service 이름 | `rada-pg` | 논리적 그룹 |
| DB Server 이름 | `rada-pg-001` | 인스턴스명. 생성 후 변경 불가 |
| VPC | `rada-vpc` | |
| Subnet | `rada-db-sn` | Private 짜리 |
| Spec | Standard 2vCPU/4GB | PoC 충분 |
| **Storage** | **SSD 30GB** | ★ 40대 14일 retention 기준. **10GB 면 7일 만에 가득** |
| 고가용성 (HA) | **OFF** | PoC. 비용 2배 |
| Multi-Zone | OFF | HA OFF 면 무관 |
| Backup | ON / 1일 1회 / 7일 보관 | |
| DB name | `pc_monitor` | ★ 정확히 |
| DB user ID | `rada` | |
| DB user password | **강한 비밀번호** | ★ 별도 저장. 16자 이상, 영대소+숫자+특수 |
| Public Domain | **OFF** | 보안 |
| Private Domain | **ON** | 내부 접근용 |

> ⚠ **DB User 의 접근 허용 CIDR** — ACG 와 **별개**의 두 번째 화이트리스트.
> User 생성 화면에 "접근 허용 IP/CIDR" 입력란 → **`10.0.1.0/24`** (App Subnet) 입력 필수.
> 둘 다 통과해야 접속됨 (ACG 통과 + User CIDR 매칭).

생성 후 **5~10분 대기**. 상태가 "운영중" 되면:
- DB Server 상세 → **Private Domain** 값 메모 (예: `pg-xxxxxx.vpc-cdb-kr.ntruss.com`)

> ⚠ **함정 — DB 의 자동 ACG**
> Cloud DB 생성 시 NCP 가 `cloud-postgresql-xxxxx` 라는 ACG 를 자동 생성하고 DB 에 부착. inbound 에는 자기 자신 (DB 관리용) 만 허용. **App VM 접근 허용은 별도 작업** (Phase 1-5 에서).

### 1-4. App VM 생성

Services → Server → 서버 생성

| 항목 | 값 | 메모 |
|---|---|---|
| 이미지 | **`ubuntu-22.04-base`** (KVM, BaseOS) | ⚠ `ubuntu-22.04-gpu` 절대 X — 5~10배 비쌈 |
| Spec | **Standard 4vCPU / 16GB** | ML + Spring + Grafana 동시 운영 여유 |
| 스토리지 | CB1 SSD **50GB** | CB1 충분 (DB I/O 가 외부라 디스크 부하 낮음) |
| VPC/Subnet | `rada-vpc` / `rada-app-sn` (Public) | |
| Public IP | **신규 할당** | 외부 접속용 |
| 물리 배치 그룹 | **미설정** | VM 1대라 무의미 |
| 반납 보호 | OFF | PoC. 발표 직전 ON 권장 |
| 서버 이름 | `rada-app-01` | |

**Login Key (.pem) — 위저드 안에서 생성**

> ⚠ **함정 — Login Key 메뉴 위치**
> Server 좌측 메뉴에 "Login Key" 항목 **없음**. 두 가지 경로 중 택일:
> 1. Server 메뉴 → 우측 상단 **"인증키 관리"** 버튼
> 2. 서버 생성 위저드의 인증키 단계 → "새로운 인증키 생성"
> 두 번째가 가장 단순.

위저드 인증키 단계:
- ◉ **새로운 인증키 생성**
- 이름: `rada-key`
- **인증키 저장** → `rada-key.pem` 자동 다운로드
- ⚠ 이 파일 분실 시 재발급 불가, VM 재생성 필요. 안전한 곳 보관 (예: `C:\Users\admin\Desktop\radaki\rada-key.pem`)

생성 후 **3~5분 대기** → 운영중 → **Public IP** 메모 (예: `223.130.x.y`)

### 1-5. ACG 정리 — App VM 측 + Cloud DB 측

#### App VM 의 ACG (기본 부착됨 — `rada-vpc-default-acg` 같은 이름)

콘솔 → ACG → 해당 ACG 클릭 → ACG 설정 → Inbound 규칙 추가:

| 프로토콜 | 접근 소스 | 허용 포트 | 메모 |
|---|---|---|---|
| TCP | `<본인 공인 IP>/32` | 22 | SSH |
| TCP | `0.0.0.0/0` | 8080 | Spring API (PoC) |
| TCP | `<본인 공인 IP>/32` | 3000 | Grafana (관리자) |

> **공인 IP 확인** — 브라우저 `https://ifconfig.me` 또는 `curl ifconfig.me`
> **금지** — 8000 (ML 내부 포트), 5432 (DB) 외부 노출 절대 X

#### Cloud DB 의 ACG (`cloud-postgresql-xxxxx` 자동 생성)

App VM 이 DB 에 접근하려면 이 ACG 에 inbound 추가:

| 프로토콜 | 접근 소스 유형 | 접근 소스 | 허용 포트 |
|---|---|---|---|
| TCP | **IP** | `10.0.1.0/24` | 5432 |

> ⚠ **함정 — 규칙 propagation 지연**
> 추가 직후 `nc -zv` 해도 BLOCKED 나올 수 있음. **1~2분 대기 후 재시도**.
> 콘솔에서 "추가" 클릭 후 화면 하단의 **"적용"** 버튼이 따로 있는 경우도 있음 — 둘 다 눌렀는지 확인.

---

## Phase 2 — App VM SSH 셋업

### 2-1. 관리자 비밀번호 발급

콘솔 → Server → `rada-app-01` → 상단 **관리자 비밀번호 확인** 버튼:

1. 인증키 (.pem) 업로드 또는 내용 붙여넣기
   ```powershell
   Get-Content C:\Users\admin\Desktop\radaki\rada-key.pem | clip
   ```
2. 비밀번호 표시됨 → 별도 저장

### 2-2. .pem 파일 권한 (Windows)

OpenSSH 는 "다른 사용자 읽기 가능" .pem 무시. 본인만 읽기로:

```powershell
$KEY = "C:\Users\admin\Desktop\radaki\rada-key.pem"
icacls $KEY /inheritance:r
icacls $KEY /grant:r "$($env:USERNAME):R"
```

> ⚠ **함정 — 권한이 갑자기 풀림**
> 윈도우 업데이트 / 백업 도구가 가끔 권한 되돌림. SSH 가 비밀번호 묻기 시작하면 위 명령 재실행. 그래도 안 풀리면 비밀번호로 로그인 → 한 번만 강제 우회.

### 2-3. SSH 접속

```powershell
ssh -i C:\Users\admin\Desktop\radaki\rada-key.pem root@<Public IP>
```

첫 접속 시 `Are you sure...` → **yes** + Enter, 비밀번호 입력 (화면에 안 보임).

성공 시 프롬프트: `root@rada-app-01:~#`

> ⚠ **함정 — 첫 로그인 시 비밀번호 변경 강제**
> NCP 가 발급한 임시 비밀번호 입력 후 새 비밀번호 입력 요구할 수 있음. 변경 후 그 새 비밀번호가 이후 root 비밀번호.

### 2-4. apt update + 도구 설치

```bash
apt update && apt upgrade -y
```

> ⚠ **함정 — apt upgrade 중 프롬프트 2종**
>
> **(A) Config file 충돌** (`/etc/issue` 등):
> ```
> *** issue (Y/I/N/O/D/Z) [default=N] ?
> ```
> → 그냥 **Enter** (default=N = 현재 유지). 모든 config 프롬프트 전부 Enter.
>
> **(B) "Daemons using outdated libraries" 다이얼로그**:
> 파란 화면에 서비스 목록 + `<Ok> <Cancel>`. → **Tab** 으로 `<Ok>` 이동 → **Enter**. ssh.service 재시작 포함되어도 기존 SSH 연결은 안 끊김 (안전).

```bash
# Docker 공식 저장소 추가 (Ubuntu 기본 저장소엔 docker-compose-plugin 없음)
apt install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update

# Docker + 도구
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
apt install -y git postgresql-client python3 python3-pip openssl python3-psycopg2

systemctl enable --now docker
docker --version
docker compose version
```

> ⚠ **함정 — `apt install docker-compose-plugin` 단독 실패**
> `E: Unable to locate package docker-compose-plugin` 에러. Ubuntu 기본 저장소 미제공. **반드시 공식 저장소 추가 후** 설치.
>
> 만약 이전에 `docker.io` 깔렸으면 충돌:
> ```bash
> dpkg -l | grep -E "^ii.*docker"      # 기존 docker.io 확인
> apt remove -y docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc
> ```

### 2-5. DB 접속 사전 검증

Spring 띄우기 전에 Cloud DB 도달 가능한지 확인.

```bash
# 1. DNS 해석
nslookup pg-xxxxxx.vpc-cdb-kr.ntruss.com
# → 10.0.2.X 사설 IP 반환되어야 정상

# 2. 포트 도달
apt install -y netcat-openbsd
nc -zv -w 5 10.0.2.X 5432
# → "Connection to ... succeeded!" 정상
```

`BLOCKED` 나면 ACG / DB User CIDR 둘 다 점검 (Phase 1-3, 1-5).

```bash
# 3. psql 실제 접속
PGPASSWORD='<DB password>' psql -h 10.0.2.X -U rada -d pc_monitor
# → pc_monitor=> 프롬프트
\q
```

> ⚠ **함정 — 비밀번호 특수문자 (`*` `$` `!` 등)**
> URL 방식 (`postgresql://user:pw@host`) 에서 특수문자가 파싱 깨짐.
> → `PGPASSWORD='...'` 환경변수 방식 사용 (작은따옴표로 감싸기).

### 2-6. 코드 클론 + .env 작성

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/Jjaerud/inha_RADA.git rada
cd rada
```

`.env` 생성 (값 안전 무작위):
```bash
PEPPER=$(openssl rand -hex 32)
GF_PW=$(openssl rand -base64 24 | tr -d /=+)

cat > /opt/rada/.env <<EOF
DB_HOST=10.0.2.X
DB_PORT=5432
DB_NAME=pc_monitor
DB_USER=rada
DB_PASSWORD=<DB 비밀번호>
DB_SCHEMA=pc_monitor

API_KEY_PEPPER=$PEPPER

GF_SECURITY_ADMIN_USER=rada_admin
GF_SECURITY_ADMIN_PASSWORD=$GF_PW
EOF

chmod 600 /opt/rada/.env

echo "PEPPER=$PEPPER"
echo "GF_PW=$GF_PW"
```

> ⚠ **함정 — heredoc 안의 변수**
> 위 `<<EOF` 는 따옴표 없어서 `$PEPPER` 등이 **이미 셸에서 치환되어** 파일에 박힘. 의도된 동작이지만, DB_PASSWORD 도 변수로 빼고 싶으면 `<<'EOF'` (따옴표) 로 막고 실행 시점에 source 하는 방식 권장.

**출력된 PEPPER / GF_PW 즉시 별도 저장** — PEPPER 는 `tools/provision_pcs.py` 가 같은 값 필요, GF_PW 는 Grafana 로그인.

### 2-7. SSH 새 세션에서 .env 자동 로드 (선택)

매 SSH 접속마다 `source .env` 귀찮으면:
```bash
echo 'set -a; source /opt/rada/.env 2>/dev/null; set +a' >> /root/.bashrc
```

다음 접속부터 변수 자동 로드 → 바로 `psql` 사용 가능.

---

## Phase 3 — Docker Compose NCP 모드

### 3-1. NCP 전용 compose 파일 작성

기존 `docker-compose.yml` 은 로컬 dev 용 (postgres 컨테이너 포함). NCP 는 Cloud DB 외부 사용:

```bash
cd /opt/rada
cat > docker-compose.ncp.yml <<'EOF'
services:
  ml-server:
    build:
      context: .
      dockerfile: ml_server/Dockerfile
    container_name: rada-ml
    environment:
      RADA_POLICY_DIR: /app/ml_server/config_yaml
      TZ: Asia/Seoul
    expose:
      - "8000"
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/status', timeout=2); sys.exit(0)\" || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 15s

  spring-server:
    build:
      context: ./server-spring
      dockerfile: Dockerfile
    container_name: rada-spring
    env_file: .env
    environment:
      SPRING_PROFILES_ACTIVE: docker
      ML_SERVER_URL: http://ml-server:8000
      TZ: Asia/Seoul
    ports:
      - "8080:8080"
    expose:
      - "8081"
    depends_on:
      ml-server:
        condition: service_started
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8081/actuator/health || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 20
      start_period: 60s

  grafana:
    image: grafana/grafana-oss:latest
    container_name: rada-grafana
    env_file: .env
    environment:
      GRAFANA_DB_USER: ${DB_USER}
      GRAFANA_DB_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
      GRAFANA_DB_HOST: ${DB_HOST}
      GRAFANA_DB_PORT: ${DB_PORT}
      GF_INSTALL_PLUGINS: marcusolsson-hexmap-panel
      TZ: Asia/Seoul
    volumes:
      - ./infra/grafana/grafana.ini:/etc/grafana/grafana.ini:ro
      - ./infra/grafana/provisioning-docker/datasources:/etc/grafana/provisioning/datasources:ro
      - ./infra/grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./infra/grafana/provisioning/alerting:/etc/grafana/provisioning/alerting:ro
      - rada_grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"

volumes:
  rada_grafana_data:
EOF
```

### 3-2. Grafana datasource — Cloud DB 가리키게 수정

원본 `provisioning-docker/datasources/postgres.yaml` 은 `url: postgres:5432` 하드코딩됨. env 치환으로:

```bash
sed -i 's|url: postgres:5432|url: ${GRAFANA_DB_HOST}:${GRAFANA_DB_PORT}|' \
  /opt/rada/infra/grafana/provisioning-docker/datasources/postgres.yaml

grep "url:" /opt/rada/infra/grafana/provisioning-docker/datasources/postgres.yaml
# → url: ${GRAFANA_DB_HOST}:${GRAFANA_DB_PORT}
```

### 3-3. compose 문법 검증

```bash
docker compose -f docker-compose.ncp.yml config > /dev/null && echo "compose OK"
docker compose -f docker-compose.ncp.yml config | grep -E "DB_HOST|GRAFANA_DB_HOST" | head -5
```

→ `compose OK` + DB_HOST 값들이 .env 의 실제 값으로 펼쳐져야 정상.

### 3-4. 첫 부팅 + Flyway

```bash
cd /opt/rada
docker compose -f docker-compose.ncp.yml up -d --build
```

빌드 5~10분. 끝나면:

```bash
docker compose -f docker-compose.ncp.yml ps
docker compose -f docker-compose.ncp.yml logs -f spring-server
```

기대 로그:
```
Flyway Community Edition ...
Migrating schema "pc_monitor" to version "1 - baseline schema"
...
Migrating schema "pc_monitor" to version "8 - align grafana reader search path"
Successfully applied 8 migrations
Started RadaApplication
```

`Started RadaApplication` 확인 후 **Ctrl+C** 로 로그 빠져나오기.

> ⚠ **함정 — Flyway `ALTER ROLE` 권한 우려**
> V6/V7/V8 가 `ALTER ROLE rada SET search_path ...` 실행. NCP managed Cloud DB 는 superuser 권한 안 줘서 실패 가능성. **실제로는 통과됨 (15.15 환경 검증)** 이지만 만약 실패하면:
> ```bash
> psql -h <DB IP> -U rada -d pc_monitor
> ALTER ROLE rada IN DATABASE pc_monitor SET search_path TO pc_monitor, public;
> DELETE FROM pc_monitor.flyway_schema_history WHERE success=false;
> \q
> docker compose -f docker-compose.ncp.yml restart spring-server
> ```

### 3-5. 검증

```bash
# 컨테이너 상태
docker compose -f docker-compose.ncp.yml ps
# → ml-server, spring-server (healthy), grafana (Up)

# Spring 헬스 (8081 내부 — 8080 은 API 전용)
docker exec rada-spring curl -fsS http://localhost:8081/actuator/health
# → {"status":"UP"}

# DB 테이블 확인
psql "postgresql://rada:'<pw>'@10.0.2.X:5432/pc_monitor" -c "\dt pc_monitor.*"
# → metrics_history, anomaly_history, pc_info, ai_judgment_history, flyway_schema_history

# Flyway 이력
psql ... -c "SELECT version, description, success FROM pc_monitor.flyway_schema_history ORDER BY installed_rank;"
# → V1, V3, V4, V5, V6, V7, V8 모두 success=t
```

> ⚠ **함정 — `curl http://localhost:8080/actuator/health` 가 500 에러**
> Spring 의 management 포트는 **8081 내부 전용** (호스트 미노출). 8080 은 API 만. **actuator 는 반드시 `docker exec rada-spring curl localhost:8081/...`** 로 호출.

---

## Phase 4 — 외부 접속 검증

### 4-1. Spring API (8080)

본인 PC PowerShell:
```powershell
curl http://<Public IP>:8080/api/metrics
```

기대: `401 Unauthorized` (API key 없어서 거부 = ✅ Spring 정상 동작).

> ⚠ **함정 — 401 / 405 가 정상**
> 200 응답이 아니어도 OK. API key 없거나 GET 요청이라 Spring 이 거부하는 것 자체가 "Spring 살아있고 외부 접근 됨" 의미.

### 4-2. Grafana (3000)

브라우저: `http://<Public IP>:3000`

로그인:
- ID: `rada_admin` (`.env` 의 GF_SECURITY_ADMIN_USER)
- PW: `.env` 의 GF_SECURITY_ADMIN_PASSWORD

대시보드 검증:
- Connections → Data sources → `RADA-Postgres` → **Save & test** → "Database Connection OK"
- Dashboards → RADA 폴더 → `rada-main` 열림

### 4-3. (학교/팀원 환경) 학내망 Grafana 허용

발표 / 데모용 학내 PC 에서 접근하려면 ACG 에 학내 CIDR 추가.

학내 PC 에서 `https://ifconfig.me` 로 학교 외부 IP 확인 (예: `165.246.x.y`).

NCP 콘솔 → ACG → App VM ACG → Inbound 추가:
| 프로토콜 | 접근 소스 | 포트 |
|---|---|---|
| TCP | `<학내 CIDR>` (예: `165.246.0.0/16`) | 3000 |

---

## Phase 5 — Retention crontab + 운영 안정화

### 5-1. Retention 스크립트

40대 × 5초 = 1.4 GB/일. 14일 보관 = 약 20GB.

```bash
cat > /opt/rada/tools/cleanup_old_data.sh <<'OUTER_EOF'
#!/bin/bash
set -e

set -a
source /opt/rada/.env
set +a

PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" <<SQL
DELETE FROM pc_monitor.metrics_history WHERE collected_at < now() - interval '14 days';
DELETE FROM pc_monitor.anomaly_history WHERE detected_at < now() - interval '90 days';
DELETE FROM pc_monitor.ai_judgment_history WHERE judged_at < now() - interval '90 days';
SQL
OUTER_EOF

chmod +x /opt/rada/tools/cleanup_old_data.sh

# 즉시 테스트 (배포 첫날이라 0 rows 삭제 기대)
/opt/rada/tools/cleanup_old_data.sh
```

> ⚠ **함정 — `ai_judgment_history` 컬럼명**
> `created_at` 아님. **`judged_at`** 이 timestamp 컬럼. 직접 `\d` 로 확인 후 사용.

```bash
# crontab 등록 — 매일 03:00 KST
( crontab -l 2>/dev/null; echo '0 3 * * * /opt/rada/tools/cleanup_old_data.sh >> /var/log/rada-cleanup.log 2>&1' ) | crontab -

crontab -l    # 확인
```

### 5-2. (선택) AI agent 활성화

Anthropic API key 발급 후 `.env` 에 추가:
```bash
echo 'ANTHROPIC_API_KEY=sk-ant-api03-...' >> /opt/rada/.env
docker compose -f docker-compose.ncp.yml restart ml-server
```

anomaly 발생 시 Claude 자동 분석 + `ai_judgment_history` 기록.
미설정 시 mock agent 사용 (코드는 동작, 분석은 placeholder).

---

## 운영 명령 모음

```bash
cd /opt/rada

# 상태
docker compose -f docker-compose.ncp.yml ps
docker exec rada-spring curl -fsS http://localhost:8081/actuator/health

# 로그
docker compose -f docker-compose.ncp.yml logs -f spring-server
docker compose -f docker-compose.ncp.yml logs -f ml-server

# 정지/시작
docker compose -f docker-compose.ncp.yml stop
docker compose -f docker-compose.ncp.yml start

# 코드 업데이트 (자세히: deploy_updates.md)
git pull
docker compose -f docker-compose.ncp.yml up -d --build

# 특정 서비스만 재빌드
docker compose -f docker-compose.ncp.yml up -d --build spring-server

# 데이터 통계
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT pc_id, MAX(collected_at), now() - MAX(collected_at) AS age
FROM pc_monitor.metrics_history GROUP BY pc_id ORDER BY MAX(collected_at) DESC LIMIT 10;"
```

---

## 자주 부딪힌 함정 모음 (요약)

| 함정 | 증상 | 해결 |
|---|---|---|
| Subnet 용도 4종 | 어느 거 고를지 헷갈림 | "일반" (Baremetal/LB/NAT 아님) |
| Login Key 메뉴 없음 | 사이드바에서 못 찾음 | Server → 우측 "인증키 관리" 또는 VM 위저드 안에서 생성 |
| ubuntu-22.04-gpu | 비싼 GPU VM 실수 선택 | `ubuntu-22.04-base` (BaseOS) |
| DB 자동 ACG 자기만 허용 | `nc -zv 5432` BLOCKED | `cloud-postgresql-xxxxx` ACG inbound 에 `10.0.1.0/24` 추가 |
| DB User CIDR | ACG 통과해도 거부 | Cloud DB User 설정에 `10.0.1.0/24` 따로 입력 |
| ACG 규칙 propagation | 추가 직후 BLOCKED | 1~2분 대기, "적용" 버튼 추가 확인 |
| `docker-compose-plugin` 없음 | apt install 실패 | Docker 공식 저장소 추가 (§2-4) |
| apt upgrade 프롬프트 | 화면 멈춤 | config 충돌 = Enter (default N), daemons = Tab → Ok Enter |
| psycopg2 missing | provision_pcs.py compose 모드 폴백 | `apt install python3-psycopg2` 또는 `pip3 install --break-system-packages psycopg2-binary` |
| Flyway ALTER ROLE | V6/V7/V8 실패 (이론상) | 실제 NCP 15.15 통과. 실패 시 수동 `ALTER ROLE rada IN DATABASE ...` |
| actuator 8080 = 500 | health check 실패로 보임 | actuator 는 8081 내부. `docker exec ... curl localhost:8081/actuator/health` |
| Grafana datasource fail | `dial tcp postgres:5432` | `provisioning-docker/datasources/postgres.yaml` 의 `url` 을 env 치환으로 (§3-2) |
| 비밀번호 특수문자 | psql URL 파싱 깨짐 | `PGPASSWORD='...'` 환경변수 사용 |
| .pem 권한 풀림 | SSH 가 비밀번호 요구 | `icacls /inheritance:r + grant:r ":R"` 재실행 |

---

## 검증 완료 = 다음 단계로

| 체크 | 확인 명령 |
|---|---|
| [ ] Spring 컨테이너 healthy | `docker compose -f docker-compose.ncp.yml ps` |
| [ ] Flyway 8 migrations success | `psql ... flyway_schema_history` |
| [ ] 외부 8080 응답 (401) | 본인 PC `curl http://<IP>:8080/api/metrics` |
| [ ] Grafana 로그인 + datasource OK | 브라우저 |
| [ ] Cloud DB 30GB | NCP 콘솔 스토리지 |
| [ ] Retention crontab 등록 | `crontab -l` |

전부 ✓ → **클라이언트 배포** 단계로:

→ [`client_deployment.md`](client_deployment.md)

## 참고

- [`deployment_checklist.md`](deployment_checklist.md) — 학생 PC 40대 배포 체크리스트
- [`fp_field_analysis_ncp.md`](../analysis/fp_field_analysis_ncp.md) — NCP 환경 FP 검증 리포트
- [`deploy_updates.md`](deploy_updates.md) — 변경사항 배포 워크플로우
- [`pc-provisioning.md`](../reference/pc-provisioning.md) — API key 발급/회전
