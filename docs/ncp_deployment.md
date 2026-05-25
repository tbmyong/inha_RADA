# NCP 배포 가이드

실제 NCP VPC 배포 과정에서 부딪힌 함정 + 정확한 해결책. 본 문서는
`docs/client_deployment.md` (클라이언트 빌드) 의 **서버 쪽 짝**.

## 0. 전제

- NCP VPC 플랫폼 (Classic 아님)
- Region: KR
- 단일 App VM + Managed Cloud DB for PostgreSQL
- HA / Multi-Zone 모두 OFF (PoC)

## 1. 콘솔 단계 — 순서대로

### 1-1. VPC + Subnet

| 리소스 | 값 | 용도 |
|---|---|---|
| VPC | `rada-vpc` / `10.0.0.0/16` | |
| Subnet `rada-app-sn` | `10.0.1.0/24` / **Public** / 용도: 일반 | App VM |
| Subnet `rada-db-sn` | `10.0.2.0/24` / **Private** / 용도: 일반 | Cloud DB |

> **함정**: 서브넷 생성 시 "용도" 가 4종 (일반/Baremetal/로드밸런서/NATGateway) — **둘 다 "일반"**. "Public/Private" 와는 다른 축. 둘 다 정해야 함.

### 1-2. Cloud DB for PostgreSQL

| 항목 | 값 | 메모 |
|---|---|---|
| Engine | **PostgreSQL 15.15** | NCP 최신. RADA 는 16 안 써도 OK |
| Service 이름 | `rada-pg` | |
| Server 이름 | `rada-pg-001` | |
| VPC / Subnet | rada-vpc / rada-db-sn | |
| Spec | Standard 2vCPU/4GB | PoC 충분 |
| Storage | **SSD 30GB** | 40대 14일 retention 기준 (원래 가이드의 10GB 는 부족) |
| HA / Multi-Zone | OFF | |
| DB name | `pc_monitor` | ★ 정확히 |
| DB user | `rada` | |
| User CIDR | `10.0.1.0/24` | ★ App Subnet 명시 |
| Public Domain | OFF | |
| Private Domain | ON | |

> **함정**: 콘솔 위저드 단계마다 다른 이름의 "ACG" 필드가 등장 (DB 의 사용자 그룹과는 별개). DB 의 자동 생성 ACG 는 `cloud-postgresql-xxxxx` — 이게 inbound 5432 룰 가지고 있는데 **자기 자신만** 허용. App VM 추가 허용은 별도 작업 (§3-2).

### 1-3. App VM

| 항목 | 값 |
|---|---|
| 이미지 | **`ubuntu-22.04-base`** (KVM, BaseOS) |
| Spec | Standard **4vCPU / 16GB** |
| 스토리지 | CB1 SSD 50GB |
| VPC/Subnet | rada-vpc / rada-app-sn |
| Public IP | 신규 할당 |
| ACG | (다음 §2 참조) |
| Login Key | 위저드 안에서 신규 생성 → .pem 다운로드 |

> **함정 1**: 이미지 목록에 `ubuntu-22.04-gpu` 가 같이 보임. **GPU 버전 금지** (5~10배 비쌈, RADA 서버는 CPU 추론).
>
> **함정 2**: VPC 콘솔에서 좌측 메뉴에 **"Login Key" 가 없음** — Server 메뉴 시작 시 우측 상단 "인증키 관리" 또는 위저드 안에서 신규 생성.
>
> **함정 3**: 위저드 마지막 "물리 배치 그룹" / "반납 보호" — 둘 다 **기본값 (미설정 / OFF)** 으로 두면 됨.

## 2. ACG 설계

### 2-1. App VM 측 — `rada-vpc-default-acg` (또는 default)

대부분의 PoC 환경에선 default ACG 그대로 사용 가능. inbound 에 다음 3개 룰 추가:

| 프로토콜 | 소스 | 포트 | 메모 |
|---|---|---|---|
| TCP | `<본인 공인 IP>/32` | 22 | SSH |
| TCP | `0.0.0.0/0` | 8080 | Spring API (PoC) |
| TCP | `<본인 공인 IP>/32` | 3000 | Grafana (관리자만) |

**금지**: 8000 (ML 내부 포트), 5432 (DB) 외부 노출.

### 2-2. DB 측 — Cloud DB 자동 ACG (`cloud-postgresql-xxxxx`)

NCP 가 DB 생성 시 자동 만들어주는 ACG. 기본 inbound 는 자기 자신만 허용. **App VM 접근 허용 추가**:

| 프로토콜 | 소스 유형 | 소스 | 포트 |
|---|---|---|---|
| TCP | **IP** | `10.0.1.0/24` | 5432 |

> **함정**: ACG 룰 추가 후 **1~2분 propagation 대기**. 즉시 테스트 시 BLOCKED 가 정상.

### 2-3. ACG 룰 검증

App VM SSH 들어간 후:

```bash
nc -zv -w 5 10.0.2.6 5432    # DB 사설 IP
```

`succeeded!` 떠야 다음 진행 가능.

## 3. App VM 초기 셋업

### 3-1. SSH 접속

```powershell
# 윈도우 PowerShell, 본인 PC
$KEY="C:\Users\admin\Desktop\radaki\rada-key.pem"
icacls $KEY /inheritance:r
icacls $KEY /grant:r "$($env:USERNAME):R"

ssh -i $KEY root@<Public IP>
```

> **함정**: 첫 SSH 시 NCP 가 발급한 관리자 비밀번호 입력 (콘솔의 "관리자 비밀번호 확인" 메뉴에서 .pem 으로 복호화). PowerShell 어디서 켜도 OK — `-i` 옵션의 절대경로만 정확하면 됨.

### 3-2. Docker — `docker.io` 가 아닌 공식 저장소

Ubuntu 기본 `docker-compose-plugin` 미제공. 공식 저장소 추가 필수:

```bash
apt update && apt upgrade -y
# upgrade 중 config-file 충돌 프롬프트는 모두 N (Enter)
# "Daemons using outdated libraries" 는 Tab → <Ok> Enter

apt install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
apt install -y git postgresql-client python3 python3-pip openssl python3-psycopg2

systemctl enable --now docker
```

> **함정**: `apt install docker-compose-plugin` 단독은 "Unable to locate package" 에러. 반드시 위 절차로 공식 저장소 추가 후 `docker-ce` 와 함께 설치.

### 3-3. 코드 + .env

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/Jjaerud/inha_RADA.git rada
cd rada

PEPPER=$(openssl rand -hex 32)
GF_PW=$(openssl rand -base64 24 | tr -d /=+)

cat > /opt/rada/.env <<EOF
DB_HOST=<Cloud DB 의 Private IP, 보통 10.0.2.X>
DB_PORT=5432
DB_NAME=pc_monitor
DB_USER=rada
DB_PASSWORD=<강한 비밀번호>
DB_SCHEMA=pc_monitor
API_KEY_PEPPER=$PEPPER
GF_SECURITY_ADMIN_USER=rada_admin
GF_SECURITY_ADMIN_PASSWORD=$GF_PW
EOF
chmod 600 /opt/rada/.env

# 출력된 PEPPER / GF_PW 별도 저장
```

> **DB_HOST**: Private Domain (예: `pg-xxxx.vpc-cdb-kr.ntruss.com`) 도 OK 지만 `getent hosts <domain>` 으로 풀린 사설 IP (10.0.2.X) 가 1~2ms 빠름.

### 3-4. DB 접속 검증

```bash
PGPASSWORD='<DB password>' psql -h <DB IP> -U rada -d pc_monitor -c "SELECT version();"
```

`PostgreSQL 15.x` 라인 나오면 OK.

## 4. Docker Compose — NCP 전용

기존 `docker-compose.yml` 은 로컬 dev 용 (postgres 컨테이너 포함). NCP 는 Cloud DB 사용하므로 분리:

```bash
cd /opt/rada
cp docker-compose.yml docker-compose.ncp.yml
```

`docker-compose.ncp.yml` 편집 — postgres 서비스 블록 전체 제거, depends_on 정리, spring/grafana 에 `env_file: .env` 추가. **완성본은 본 repo 의 동일 파일 참조**.

추가: Grafana datasource 의 호스트도 Cloud DB 가리키게 수정:

```bash
sed -i 's|url: postgres:5432|url: ${GRAFANA_DB_HOST}:${GRAFANA_DB_PORT}|' \
  /opt/rada/infra/grafana/provisioning-docker/datasources/postgres.yaml
```

`.env` 에 `GRAFANA_DB_HOST` 추가 (DB_HOST 와 동일 값) — `docker-compose.ncp.yml` 의 environment 블록에서 자동 매핑.

검증:

```bash
docker compose -f docker-compose.ncp.yml config > /dev/null && echo "compose OK"
```

## 5. 첫 부팅 + Flyway

```bash
cd /opt/rada
docker compose -f docker-compose.ncp.yml up -d --build
docker compose -f docker-compose.ncp.yml logs -f spring-server
```

기대:
```
Successfully applied 8 migrations
Started RadaApplication
```

**Flyway `ALTER ROLE` 실패 시** (NCP managed DB 제약):
```sql
-- 직접 접속해서 user search_path 설정
psql ...
ALTER ROLE rada IN DATABASE pc_monitor SET search_path TO pc_monitor, public;
DELETE FROM pc_monitor.flyway_schema_history WHERE success=false;
```
→ Spring 재시작.

> NCP 15.15 환경에선 통과 확인됨. 추후 버전에서 변경될 수 있음.

검증 (`actuator/health` 는 8081 내부 포트):

```bash
docker exec rada-spring curl -fsS http://localhost:8081/actuator/health
# {"status":"UP"}

# 본인 PC PowerShell 에서
curl http://<Public IP>:8080/api/metrics    # 401 = OK (API key 없음)
```

## 6. API key 발급 + 클라이언트 시범

VM 에서:

```bash
cd /opt/rada
set -a; source .env; set +a

python3 tools/provision_pcs.py \
  --count 1 --prefix dev \
  --output /tmp/keys.csv \
  --db-url "postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

cat /tmp/keys.csv     # raw_key 메모 후
shred -u /tmp/keys.csv
```

> **함정**: `--from-compose` 옵션은 docker compose 안에 postgres 컨테이너가 있다는 가정 — NCP 환경에선 반드시 `--db-url` 사용.

## 7. 운영 명령

```bash
cd /opt/rada

# 정지/시작
docker compose -f docker-compose.ncp.yml stop
docker compose -f docker-compose.ncp.yml start

# 로그
docker compose -f docker-compose.ncp.yml logs -f spring-server
docker compose -f docker-compose.ncp.yml logs -f ml-server

# 코드 업데이트
git pull
docker compose -f docker-compose.ncp.yml up -d --build

# 특정 서비스만 재빌드
docker compose -f docker-compose.ncp.yml up -d --build spring-server
```

## 8. Retention (40대 배포 전 필수)

40대 5초 주기 = 약 **1.4 GB/일**. 10GB 스토리지 7일 만에 가득. 다음 둘 중 선택:

**A. 스토리지 30GB + 14일 retention (권장)**

NCP 콘솔에서 Cloud DB 스토리지 확장 후, crontab 등록:

```bash
crontab -e
# 매일 03:00 KST 정리
0 3 * * * PGPASSWORD='<pw>' psql -h <DB IP> -U rada -d pc_monitor -c "DELETE FROM pc_monitor.metrics_history WHERE collected_at < now() - interval '14 days'; DELETE FROM pc_monitor.anomaly_history WHERE detected_at < now() - interval '90 days';"
```

**B. 5초 → 1분 집계 + 원본 폐기 (장기 운영)**

별도 ETL job 필요 (현재 범위 밖).

## 9. 자주 부딪힌 함정 모음

| 함정 | 증상 | 해결 |
|---|---|---|
| `docker-compose-plugin` 패키지 없음 | apt install 실패 | 공식 저장소 추가 (§3-2) |
| Cloud DB 5432 BLOCKED | `nc -zv` timeout | DB 자동 ACG 에 `10.0.1.0/24 → 5432` inbound 추가 (§2-2) |
| Cloud DB ACG 룰 즉시 안 통함 | 추가 직후 BLOCKED | 1~2분 propagation 대기 |
| `actuator/health` on 8080 = 500 | InternalServerError | actuator 는 내부 8081 — `docker exec ... curl localhost:8081/actuator/health` |
| Grafana 가 postgres 호스트 못 찾음 | datasource test fail | `infra/grafana/provisioning-docker/datasources/postgres.yaml` 의 `url` 을 `${GRAFANA_DB_HOST}` 로 (§4) |
| psycopg2 없음 | provision_pcs.py 가 compose 모드 폴백 | `pip3 install psycopg2-binary` 또는 `apt install python3-psycopg2` |
| 비밀번호 특수문자 | psql URL 파싱 실패 | `PGPASSWORD='...'` 환경변수 방식으로 분리 |
| Flyway `ALTER ROLE` 실패 | V6/V7/V8 fail | §5 수동 우회 |

## 10. 참고

- `docs/client_deployment.md` — PyInstaller 빌드 + Task Scheduler
- `docs/pc-provisioning.md` — API key 발급/회전
- `docs/team-guide.md` — Fork 워크플로우
- `docs/fp_field_analysis_post_p2.md` — 단일 PC FP 검증 (배포 후 다수 PC 결과와 비교 기준)
