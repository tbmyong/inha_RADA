# RADA NCP 인프라 셋업 가이드

대상: NCP Compact / Standard 단일 서버 (Ubuntu 22.04, 4GB RAM, 2 vCPU 가정).
구성:
- Spring Boot API (`:8080`, 외부 노출)
- FastAPI ML 서버 (`127.0.0.1:8000`, 내부 전용)
- PostgreSQL 15 (`localhost:5432`, 내부 전용)
- Grafana OSS (`:3000`, 외부 노출)

## 셋업 순서 (5 단계)

각 스크립트는 `infra/ncp/scripts/` 하위에 있다. 서버에 업로드 후 순서대로 실행한다.

### 1. ACG 규칙 설정 — `01-acg-setup.md`
NCP 콘솔에서 ACG 를 다음과 같이 구성한다.
- 외부 허용: `22` (관리자 IP 한정), `8080`, `3000`
- 외부 차단(ACG 비등록): `8000`, `5432`

### 2. PostgreSQL 설치/튜닝 — `02-install-postgres.sh`
```
sudo DB_OWNER_PASSWORD='strong_app_pw' bash 02-install-postgres.sh
```
- `shared_buffers=128MB`, `effective_cache_size=1GB`, `max_connections=50`
- `listen_addresses='localhost'` 로 외부 차단
- DB(`pc_monitor`) 와 OWNER(`rada_app`) 만 생성. 테이블 DDL 은 백엔드 측에서 수행.

### 3. Grafana 전용 READ-ONLY 계정 생성 — `03-create-grafana-reader.sh`
```
sudo GRAFANA_READER_PASSWORD='strong_reader_pw' bash 03-create-grafana-reader.sh
```
- `grafana_reader` 역할 + `GRANT SELECT` 만 부여
- `ALTER DEFAULT PRIVILEGES` 로 향후 추가 테이블도 자동 SELECT 권한

### 4. JDK 17 + Grafana 설치 — `04-install-jdk-grafana.sh`
```
sudo bash 04-install-jdk-grafana.sh
```
설치 후 다음 파일을 서버로 배포한다.
- `infra/grafana/grafana.ini`           → `/etc/grafana/grafana.ini`
- `infra/grafana/provisioning/...`      → `/etc/grafana/provisioning/...`
- `infra/ncp/systemd/grafana-server.override.conf`
  → `/etc/systemd/system/grafana-server.service.d/override.conf`
  (`GRAFANA_READER_PASSWORD` 환경변수 주입)

### 5. 시스템 타임존 = UTC — `05-timezone-setup.sh`
```
sudo bash 05-timezone-setup.sh
```
시스템/DB 는 UTC, Grafana 표시는 Asia/Seoul.

### (부가) systemd / logrotate 설치
```
sudo cp infra/ncp/systemd/rada-springboot.service /etc/systemd/system/
sudo cp infra/ncp/systemd/rada-fastapi.service    /etc/systemd/system/
sudo cp infra/ncp/logrotate/rada                  /etc/logrotate.d/rada
sudo useradd -r -s /usr/sbin/nologin rada || true
sudo install -d -o rada -g rada /var/log/rada /opt/rada
sudo systemctl daemon-reload
sudo systemctl enable --now rada-springboot rada-fastapi
```

## 검증 절차

### 1) 외부 포트 차단 확인 (다른 머신에서)
```
nc -zv <외부IP> 8000   # FAIL 이어야 함 (timeout / connection refused)
nc -zv <외부IP> 5432   # FAIL 이어야 함
nc -zv <외부IP> 8080   # OK
nc -zv <외부IP> 3000   # OK
```
8000/5432 가 한 번이라도 열리면 ACG → uvicorn `--host` → `listen_addresses` 순으로 점검한다.

### 2) Grafana DataSource Test
- `http://<외부IP>:3000` 접속 → 로그인
- Connections → Data sources → `RADA-Postgres` → `Save & test`
- "Database Connection OK" 응답 확인. 실패 시 `journalctl -u grafana-server` 의 `pq:` 라인을 본다.

### 3) AlertRule firing 시뮬레이션
백엔드 V3 스키마 기준 `anomaly_history` 테이블이 존재한다는 가정.
```
sudo -u postgres psql -d pc_monitor -c "
INSERT INTO anomaly_history (pc_id, detected_at, severity, anomaly_type, message)
VALUES ('PC-TEST', NOW(), 'HIGH', 'cpu_spike', 'simulation');"
```
- Grafana → Alerting → Alert rules → `RADA High Risk Detected`
- 1 분 내 `Pending` → `for: 1m` 경과 후 `Firing` 으로 전이하는지 확인.
- 종료 시 위 INSERT 한 행을 삭제하면 5 분 후 자동 Resolved.

### 4) 메모리 분배 확인
```
free -m
# 권장 분배 (4096MB 기준)
#  Spring Boot   : -Xmx512m  (실 사용 ~600MB)
#  FastAPI       : ~500MB
#  PostgreSQL    : shared_buffers 128MB + 워크메모리 ~150MB
#  Grafana       : MemoryMax 512MB
#  OS / 버퍼     : 잔여
ps -o rss=,cmd= -C java,uvicorn,grafana-server,postgres | sort -nr | head -20
```

## 스키마 매핑 (V5 확정)

A팀 Spring JPA 엔티티 기준 V5 스키마. Grafana SQL 은 본 매핑에 정합한다.

### `metrics_history` (시계열 리소스 메트릭)
| 컬럼 | 타입 / 설명 |
|------|-------------|
| `pc_id` | text, FK → pc_info.pc_id |
| `collected_at` | timestamptz, 수집 시각 |
| `cpu_percent` | double precision (구 `cpu_usage`) |
| `mem_percent` | double precision (구 `memory_usage`) |
| `disk_read_mb` | double precision (구 `disk_usage` 분리) |
| `disk_write_mb` | double precision (구 `disk_usage` 분리) |
| `inbound_mb` | double precision (구 `network_in`) |
| `outbound_mb` | double precision (구 `network_out`) |
| `gpu_percent` | double precision (V3 신규) |
| `vram_mb` | double precision (V3 신규) |
| `extra` | jsonb |
| (인덱스) | 복합 인덱스 `(pc_id, collected_at)` V3 신규 |

### `anomaly_history`
| 컬럼 | 타입 / 설명 |
|------|-------------|
| `id` | bigserial PK |
| `pc_id` | text |
| `detected_at` | timestamptz |
| `severity` | text — `NORMAL` / `LOW` / `MEDIUM` / `HIGH` (V5) |
| `anomaly_type` | text — ML/룰 원본 verdict 보존 (`mining_suspected`, `gpu_burst` 등) |
| `message` | text |
| `scores` | jsonb |
| `alerts` | jsonb |

### `ai_judgment_history`
| 컬럼 | 타입 / 설명 |
|------|-------------|
| `pc_id` | text |
| `judged_at` | timestamptz |
| `anomaly_id` | bigint FK → anomaly_history.id |
| `model_name` | text |
| `verdict` | text |
| `confidence` | double precision |
| `judgment` | text (V5 신규, 직접 컬럼) |
| `severity` | text (V5 신규, 직접 컬럼 — `NORMAL`/`LOW`/`MEDIUM`/`HIGH`) |
| `reason` | text (V5 신규, 직접 컬럼) |
| `action` | text (V5 신규, 직접 컬럼) |
| `is_mock` | boolean (V5 신규, 직접 컬럼) |
| `details` | jsonb (V5 이후 보조용 — 직접 컬럼 우선 사용) |

### `pc_info`
| 컬럼 | 타입 / 설명 |
|------|-------------|
| `pc_id` | text PK |
| `hostname` | text |
| `api_key` | text |
| `is_active` | boolean |
| `registered_at` | timestamptz |
| `last_seen_at` | timestamptz |
| `location` | text (V5 신규) |
| `gpu_available` | boolean (V5 신규) |

### severity 색상 매핑 (Grafana)
| severity | 라벨 | 색상 |
|----------|------|------|
| `NORMAL` | 정상 | green |
| `LOW` | 관찰 | light-yellow |
| `MEDIUM` | 점검 필요 | yellow |
| `HIGH` | 위험 | red |

### FK 제약 안내
`anomaly_history.pc_id`, `ai_judgment_history.anomaly_id` 등 V5 신규 FK 는
기존 데이터 호환성을 위해 `NOT VALID` 로 추가될 수 있다. Grafana SQL 은
`JOIN` 시 NULL 매칭이 발생할 수 있음을 가정하고 작성한다.

### $slot 변수 제거 안내
V5 정합화 라운드에서 메인 대시보드의 `$slot` 템플릿 변수를 제거했다 (스키마 미연동).
수업/자율 슬롯 기능은 향후 백엔드 컬럼이 합류한 뒤 재도입한다.

## 1단계 계약 정합 (P0)

1단계(P0) 라운드에서 백엔드/ML 간 JSONB 페이로드 계약이 확정되었다. Grafana SQL 은
다음 호환 우선순위 / 문자열 enum 을 가정하고 작성된다. DDL 변경은 없으며 SELECT 측
COALESCE / CASE 만 정합화한다.

### `anomaly_history.scores` JSONB 구조

ML 서버 버전별로 score 키 위치가 다르므로, Grafana 의 anomaly_score 추출은 다음
**호환 우선순위** 를 따른다 (NULL 이면 다음 후보로 fallback).

1. `scores->'score_breakdown'->>'final'` — 1단계 신규 정식 위치 (final score)
2. `scores->>'final'` — 중간 단계 호환
3. `scores->>'total'` — 레거시 V3/V4 호환
4. `0` — 모두 NULL 일 때 기본값

예시 페이로드:
```json
{
  "score_breakdown": { "final": 42.5, "cpu": 30.0, "gpu": 12.5 },
  "final": 42.5,
  "total": 42.5
}
```

#### `score_breakdown` 8키 의미

1단계(P0)에서는 일부 키가 0 placeholder 일 수 있으며, B가 3단계에서 실제 값을 채운다.

| key | 의미 | 비고 |
|-----|------|------|
| resource | CPU/MEM/GPU/VRAM 자원 기반 부분 점수 | 룰 + 통계 |
| network | inbound/outbound 트래픽 이상 부분 점수 | 룰 |
| process | top_processes 분포 / 신규 프로세스 부분 점수 | 룰 |
| episode | 연속 이상 에피소드 가중치 | 시계열 누적 |
| correlation | 자원-네트워크-프로세스 상관 점수 | 룰 |
| ml | FastAPI ML 모델 부분 점수 | 모델 의존 |
| context_discount | 학습/회의 시간대 등 컨텍스트 감산값 (음수 가능) | 룰 |
| final | 최종 합산 점수 (Grafana anomaly_score 표시 기준) | severity 산출에 사용 |

Grafana `rada-pc-detail` 패널 id=7 은 위 8키를 다음 SQL 로 추출한다 (NULL 은 0 placeholder):

```sql
SELECT
  COALESCE((scores->'score_breakdown'->>'resource')::float, 0)         AS resource,
  COALESCE((scores->'score_breakdown'->>'network')::float, 0)          AS network,
  COALESCE((scores->'score_breakdown'->>'process')::float, 0)          AS process,
  COALESCE((scores->'score_breakdown'->>'episode')::float, 0)          AS episode,
  COALESCE((scores->'score_breakdown'->>'correlation')::float, 0)      AS correlation,
  COALESCE((scores->'score_breakdown'->>'ml')::float, 0)               AS ml,
  COALESCE((scores->'score_breakdown'->>'context_discount')::float, 0) AS context_discount,
  COALESCE((scores->'score_breakdown'->>'final')::float, 0)            AS final
FROM anomaly_history
WHERE pc_id = '$pc_id' AND $__timeFilter(detected_at)
ORDER BY detected_at DESC
LIMIT 1;
```

### `ai_judgment_history.verdict` 4단계 enum

| verdict | 의미 |
|---------|------|
| `NORMAL` | 이상 없음 |
| `OBSERVE` | 관찰 필요 (저위험) |
| `SUSPICIOUS` | 의심 (중위험) |
| `HIGH_RISK` | 고위험 (즉시 조치) |

Grafana 표시/색상 매핑 시 위 4단계 문자열을 그대로 사용한다. severity 컬럼
(`NORMAL`/`LOW`/`MEDIUM`/`HIGH`) 과는 별개 enum 이며, 매핑 변경은 본 라운드 범위 밖.

### `hw_degradation` 문자열 enum

ML/AI 판정의 하드웨어 열화 상태는 다음 3단계 문자열 enum 으로 통일한다.

| 값 | 의미 |
|----|------|
| `NONE` | 열화 징후 없음 |
| `SUSPECTED` | 열화 의심 |
| `CONFIRMED` | 열화 확정 |

JSONB 페이로드 내 `hw_degradation` 키 또는 별도 컬럼으로 노출될 경우 모두 위
문자열 값을 가정한다 (boolean / 정수 코드 아님).

### TTL / 보존 정책
- `metrics_history` 만 **30 일 보존** 으로 A팀 Spring `@Scheduled` 가 주기 삭제한다.
- `anomaly_history`, `ai_judgment_history` 의 보존 기간은 V5 시점에는 미정 — 향후 검토.
- 인프라 측 cron / pg_partman 은 사용하지 않는다.

## 의존성 / 한계

- 본 인프라 코드는 **DDL 을 수행하지 않는다.** (`CREATE TABLE`, `ALTER`, 인덱스 정의 없음.)
  - `(pc_id, collected_at)` 복합 인덱스는 A팀 JPA `@Index` 선언에 의존한다.
- AlertRule contact point (`grafana-notifiers` / Slack / Email) 는 별도 라운드에서 작업한다.
  현재는 firing 상태만 Grafana UI 에서 확인 가능.
- 단일 서버 구성이므로 가용성/백업은 별도로 설계해야 한다 (NCP Object Storage 로
  `pg_dump` 일일 업로드 권장).
- Grafana 초기 admin 비밀번호(`grafana.ini`)는 최초 로그인 시 즉시 변경할 것.
