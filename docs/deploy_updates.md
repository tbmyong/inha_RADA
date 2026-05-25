# 변경사항 배포 워크플로우

> **이전 단계**: [`deployment_checklist.md`](deployment_checklist.md) (학생 PC 40대 배포 완료, 운영 시작됨)

코드/대시보드/ML 알고리즘 변경 시 **개발자 PC → GitHub → NCP App VM → 학생 PC** 까지 흘러가는 표준 절차.

작업 순서 (전체 흐름):

```
[github_setup.md]  →  [ncp_deployment.md]  →  [client_deployment.md]  →  [deployment_checklist.md]  →  ★ [deploy_updates.md] ★
```

운영 중 어떤 종류의 변경이든 본 문서가 SSOT.

## 0. 단일 진실 원천 (SSOT)

GitHub `main` 브랜치가 운영 환경의 SSOT. NCP VM 은 `git pull` 로만
업데이트한다. **NCP VM 안에서 직접 수정 금지** — 다음 pull 때 덮어쓰임.

## 1. 변경 유형별 배포 절차

### A. Spring / ML / 클라이언트 코드 수정

```
[로컬]
1. 코드 수정 + 로컬 테스트
2. git add ... && git commit && git push origin main

[NCP VM]
3. ssh root@<Public IP>
4. cd /opt/rada && git pull
5. docker compose -f docker-compose.ncp.yml up -d --build <service>
   - spring 만 바뀜:  --build spring-server
   - ml 만 바뀜:      --build ml-server
   - 둘 다:           --build spring-server ml-server
6. docker compose -f docker-compose.ncp.yml logs -f <service>
   - 부팅 정상 확인 후 Ctrl+C
```

**무중단 빌드 — 한 줄 명령**:
```bash
cd /opt/rada && git pull && docker compose -f docker-compose.ncp.yml up -d --build
```

### B. Grafana 대시보드 / 패널 수정

대시보드는 JSON 파일로 provisioning-mount 됨:
- 경로: `infra/grafana/provisioning/dashboards/*.json`

**방법 1 — 콘솔에서 편집 후 export (권장)**

```
[Grafana UI]
1. 패널 편집 → Save dashboard
2. 우상단 ⚙ → JSON Model → 전체 복사
3. infra/grafana/provisioning/dashboards/<name>.json 에 붙여넣기

[로컬]
4. git diff → 변경 확인 후 commit + push

[NCP VM]
5. git pull
6. docker compose -f docker-compose.ncp.yml restart grafana
   (재빌드 불필요 — 파일만 다시 읽음)
```

**방법 2 — JSON 직접 수정**
- 익숙한 사람만. 패널 좌표 / queries / thresholds 등.

### C. 데이터소스 / Alert 룰 수정

```
[로컬]
1. infra/grafana/provisioning-docker/datasources/postgres.yaml
   또는 infra/grafana/provisioning/alerting/*.yaml 수정
2. git push

[NCP VM]
3. git pull
4. docker compose -f docker-compose.ncp.yml restart grafana
```

### D. Scoring Policy (`ml_server/config_yaml/scoring_policy.yaml`)

ML 서버가 부팅 시 한 번 로드:

```
[로컬]
1. ml_server/config_yaml/scoring_policy.yaml 수정 + 단위테스트
2. git push

[NCP VM]
3. git pull
4. docker compose -f docker-compose.ncp.yml restart ml-server
   (재빌드 불필요 — yaml 만 mount-read)
```

> **검증 필수**: scoring 변경은 FP 율에 직접 영향. 본인 PC 1대로 1시간 이상 정상 사용 후 anomaly_history 확인.

### E. 클라이언트 (`client_core/`, `client.py`) 수정

학생 PC 에 배포된 `.exe` 까지 흘러가야 함:

```
[로컬]
1. 코드 수정 + 단위테스트
2. git push

[NCP VM] (서버 재시작 불필요)
   → 변경 없음. 서버는 client 코드를 모름.

[빌드 PC]
3. cd C:\Users\admin\Desktop\rada
4. git pull
5. pyinstaller --onefile --noconsole --name rada_client \
     --hidden-import pynvml --hidden-import GPUtil \
     --collect-all client_core client.py

[학생 PC 배포]
6. 새 dist\rada_client.exe 를 학생 PC 의 C:\ProgramData\RADA\ 에 덮어쓰기
7. schtasks /End /TN "RADA Client"
8. schtasks /Run /TN "RADA Client"
```

40대 배포는 **공유폴더에 신규 exe 두고 자동 업데이트 스크립트 (다음 §3)** 사용 권장.

### F. DB 스키마 변경

Flyway migration 추가:

```
[로컬]
1. server-spring/src/main/resources/db/migration/V9__<name>.sql 작성
   - V8 이후 다음 번호
   - 멱등 (idempotent) 으로 작성. `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
2. 로컬 docker compose 에서 Spring 재기동 → migration 검증
3. git push

[NCP VM]
4. git pull
5. docker compose -f docker-compose.ncp.yml up -d --build spring-server
   - Spring 부팅 시 Flyway 가 자동 적용
6. logs 에서 "Migrating schema ... to version 9" 확인
```

> **함정**: NCP managed DB 는 `ALTER ROLE`, `CREATE EXTENSION` 권한 제약 가능. 새 migration 작성 시 미리 권한 필요 여부 확인 (`postgres_fdw`, `pg_stat_statements` 등은 NCP 가 차단).

## 2. 롤백 절차

### 코드 롤백
```
[로컬]
git revert <bad-commit>
git push

[NCP VM]
git pull
docker compose -f docker-compose.ncp.yml up -d --build
```

### DB migration 롤백
Flyway 는 자동 down-migration 없음. **수동 SQL 작성** 후 새 V 번호로 push.

## 3. 학생 PC 일괄 업데이트 (운영 단계)

배포 PC 각각이 부팅 시 `\\<share>\rada\rada_client.exe` 와 자기 `C:\ProgramData\RADA\rada_client.exe` 비교 → 다르면 복사 + Task 재시작.

`auto-update.bat` (Task Scheduler ONLOGON 시 install.bat 대신 사용):
```bat
@echo off
set SRC=\\<file-server>\rada\rada_client.exe
set DST=C:\ProgramData\RADA\rada_client.exe
fc /b "%SRC%" "%DST%" >nul 2>&1
if errorlevel 1 (
    schtasks /End /TN "RADA Client" >nul 2>&1
    copy /Y "%SRC%" "%DST%" >nul
    schtasks /Run /TN "RADA Client" >nul
)
```

→ Task Scheduler 등록 시 `auto-update.bat` 를 `rada_client.exe` 시작 전에 호출.

## 4. 배포 순서 (변경 영향 범위 따라)

| 변경 | 영향 | 권장 순서 |
|---|---|---|
| Grafana JSON | 시각화만 | 즉시 NCP restart grafana |
| Scoring yaml | FP/탐지율 | 본인 PC 1h 검증 → NCP restart ml-server → 24h 관찰 |
| ML 알고리즘 (코드) | 점수 계산 | 단위테스트 → NCP build ml-server → 본인 PC 1대 1일 → 학생 PC |
| Spring 코드 | API 동작 | 단위테스트 → NCP build spring-server → 즉시 curl 검증 |
| 클라이언트 코드 | metric 수집 | exe 재빌드 → 본인 PC 시범 → 학생 PC 점진 |
| DB schema | 영구 변경 | Flyway migration → NCP build spring-server → migration 로그 확인 |

## 5. 점검 명령 모음

```bash
# 컨테이너 상태 (NCP)
docker compose -f docker-compose.ncp.yml ps

# Spring 헬스
docker exec rada-spring curl -fsS http://localhost:8081/actuator/health

# ML 헬스
docker exec rada-ml curl -fsS http://localhost:8000/status

# DB
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
  -c "SELECT pc_id, MAX(collected_at) FROM pc_monitor.metrics_history GROUP BY pc_id;"

# 디스크 사용량 (retention 모니터링)
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
  -c "SELECT pg_size_pretty(pg_total_relation_size('pc_monitor.metrics_history'));"
```
