# RADA 배포 최종 체크리스트

> **이전 단계**: [`client_deployment.md`](client_deployment.md) (Phase 1~4 — 빌드 + 시범 + 패키지)
> **다음 단계**: [`deploy_updates.md`](deploy_updates.md) (운영 중 변경사항 배포)

NCP 배포 + 학생 PC 운영 직전 체크리스트. 본 문서를 따라 순서대로 진행하면 학생 PC 40대 배포 + 운영 안정화까지 완료됨.

작업 순서 (선행 → 본 문서 → 후행):

```
[github_setup.md]  →  [ncp_deployment.md]  →  [client_deployment.md]  →  ★ [deployment_checklist.md] ★  →  [deploy_updates.md]
```

본 문서의 짝:
- [`ncp_deployment.md`](ncp_deployment.md) — NCP 서버 셋업 (선행 완료)
- [`client_deployment.md`](client_deployment.md) — 클라이언트 빌드/배포 매뉴얼 (선행 완료)
- [`deploy_updates.md`](deploy_updates.md) — 운영 중 변경사항 배포 절차 (후행)
- [`fp_field_analysis_ncp.md`](fp_field_analysis_ncp.md) — NCP 환경 FP 검증 결과 (참고)

---

## 1. 학생 PC 40대 배포 (실습실)

### 1-1. 배포 패키지 준비

`C:\Users\admin\Desktop\RADA-deploy\` 전체를:
- **USB 1개** (마스터 백업)
- **D:\RADA-deploy\** (실습실 PC 작업 편리)

포함 파일 4개:
- `install.bat` — 설치 자동화
- `rada_client.exe` — 클라이언트 본체 (~22 MB)
- `keys.csv` — PC-01 ~ PC-40 API key 목록 (평문 — 보안 주의)
- `README.txt` — PC 1대당 작업 절차

### 1-2. PC 1대당 표준 절차

```
1. install.bat 우클릭 → "관리자 권한으로 실행"
2. "Enter PC number" 프롬프트 → 01, 02, ... 40 입력
3. [OK] PC-XX installed and running in background. 메시지 확인
4. 관리자 cmd 에서:
     schtasks /End /TN "RADA Client"
     taskkill /F /IM rada_client.exe
5. 마에스트로로 baseline 이미지 저장
6. 다음 PC
```

PC 1대당 약 1분 → 40대 = 약 40분.

### 1-3. 마에스트로 (이미지 복구 SW) 호환성

이미지 안에 포함되는 것:
- `C:\ProgramData\RADA\rada_client.exe`
- `%APPDATA%\rada\config.yaml` (PC-XX 의 api_key 박힘)
- Task Scheduler "RADA Client" (ONLOGON 트리거)

복원 시 흐름:
```
PC 부팅 → 학생 로그인 → Task Scheduler ONLOGON → rada_client.exe 자동 실행
→ 5초마다 metric 수집 → NCP 로 전송
```

학생 PC 환경에 대한 가정:
- **A 케이스 (PC 별 자기 이미지 보관/복원)**: 본 매뉴얼 그대로 적용 가능 ✓
- **B 케이스 (마스터 이미지 1개 → 40 클론)**: 모든 PC 가 같은 api_key 가짐 → 별도 해결책 필요 (현 매뉴얼 부적합)

---

## 2. NCP 콘솔 작업 (학교에서 한 번에)

학교 PC 에서 `https://ifconfig.me` 로 학내망 외부 IP 확인 후:

### 2-1. Grafana 학내망 허용 (3000)

콘솔 → ACG → `rada-vpc-default-acg` → Inbound 규칙 추가:

| 프로토콜 | 접근 소스 유형 | 접근 소스 | 허용 포트 | 메모 |
|---|---|---|---|---|
| TCP | IP | `<학내 CIDR>` (예: `165.246.0.0/16`) | 3000 | Grafana 학내망 |

### 2-2. (선택) SSH 학내망 허용 (22)

학교에서도 SSH 작업 하려면 같은 ACG 에:

| 프로토콜 | 접근 소스 유형 | 접근 소스 | 허용 포트 | 메모 |
|---|---|---|---|---|
| TCP | IP | `<학내 CIDR>` | 22 | SSH 학내망 |

### 2-3. Cloud DB 스토리지 30GB 확장

콘솔 → Cloud DB for PostgreSQL → `rada-pg-001` → "스토리지 확장":
- 현재: 10 GB
- 변경: **30 GB**
- 다운타임 없이 3~5분 내 적용

---

## 3. 배포 후 검증 (NCP VM SSH)

```bash
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT pc_id, MAX(collected_at) AS last,
       now() - MAX(collected_at) AS age
FROM pc_monitor.metrics_history
WHERE pc_id LIKE 'PC-%'
GROUP BY pc_id ORDER BY pc_id;"
```

기대:
- 40개 PC 행 (PC-01 ~ PC-40)
- 각 행의 `age` 가 5~10초 이내

배포 시점에 따라 일부 PC 가 절전/꺼짐 상태일 수 있음. 그 경우 해당 PC 만 age 가 길거나 행이 없음.

---

## 4. 보안 정리 (배포 끝난 후 즉시)

### 4-1. raw_key 평문 파일 폐기

```powershell
# 본인 PC
Remove-Item C:\Users\admin\Desktop\RADA-deploy\keys.csv
Remove-Item C:\Users\admin\Desktop\student_keys.csv
```

USB / D: 의 keys.csv 도 모두 삭제. 학생 PC 의 D 드라이브에 RADA-deploy 폴더 두고 작업했으면 그 keys.csv 도 이미지 저장 전 삭제 (README.txt 의 보안 주의 참조).

### 4-2. NCP VM 측 임시 파일 확인

```bash
ls /tmp/student_keys.csv /tmp/trigger_keys.csv 2>&1
# "No such file" 두 개 다 나와야 정상 (이전에 shred 함)
```

---

## 5. (선택) 추가 개선 — 시간 여유에 따라

| 우선순위 | 작업 | 효과 | 소요 |
|---|---|---|---|
| 중 | AI agent 활성화 | Anthropic API key 발급 → `.env` 의 `ANTHROPIC_API_KEY` 추가 → `docker compose ... restart ml-server` → anomaly 발화 시 Claude 자동 판단 | 15분 |
| 중 | Grafana 패널 미화 | UI 에서 패널 편집 → JSON Model export → repo 의 `infra/grafana/provisioning/dashboards/` 업데이트 → `git push` → NCP `git pull && docker compose ... restart grafana` | 1~2h |
| 낮 | 2주 long-run 분석 리포트 | 40 PC × 2주 데이터 → `docs/fp_field_analysis_lab.md` 작성 (P2/NCP 단계의 후속) | 1일 |
| 낮 | Watchdog Task | 학생이 작업관리자에서 client 죽인 경우 5분 내 자동 부활 | 10분 |
| 낮 | Pyinstaller 빌드 매니페스트 갱신 | client 코드 변경 시 새 exe 빌드 → 학생 PC 마에스트로 이미지 재저장 | 변경 시 |

### 5-1. AI agent 활성화 절차

```bash
# NCP VM SSH 에서
echo 'ANTHROPIC_API_KEY=sk-ant-api03-...' >> /opt/rada/.env
docker compose -f docker-compose.ncp.yml restart ml-server

# anomaly 발생 시 ai_judgment_history 에 기록되는지
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT pc_id, model_name, verdict, judged_at FROM pc_monitor.ai_judgment_history
ORDER BY judged_at DESC LIMIT 5;"
```

비용: Claude Haiku 기준 anomaly 1건당 약 $0.001. 40 PC × 일 1건 가정 시 약 $0.04/일.

### 5-2. Grafana 패널 미화 워크플로우

```
[Grafana UI]
  ⚙ 아이콘 → JSON Model → 전체 복사

[로컬]
  infra/grafana/provisioning/dashboards/rada-main.json (또는 rada-pc-detail.json) 에 붙여넣기
  git add ... && git commit -m "grafana(main): <변경 내용>" && git push

[NCP VM]
  cd /opt/rada && git pull
  docker compose -f docker-compose.ncp.yml restart grafana
```

재빌드 불필요 — JSON 만 mount-read.

### 5-3. Watchdog Task (관리자 PowerShell — 본인 PC 검증용)

```powershell
schtasks /Create /TN "RADA Watchdog" `
  /TR "powershell -NoProfile -WindowStyle Hidden -Command \"if (-not (Get-Process rada_client -EA SilentlyContinue)) { Start-Process 'C:\ProgramData\RADA\rada_client.exe' -WindowStyle Hidden }\"" `
  /SC MINUTE /MO 5 /RL HIGHEST /F
```

5분마다 살아있는지 체크. 학생 PC 배포 시 install.bat 에 추가하면 모든 PC 에 자동 적용 (다음 빌드 PR 에 포함 권장).

---

## 6. 발표 직전 점검

| 항목 | 확인 명령 |
|---|---|
| NCP VM 운영중 | NCP 콘솔 또는 `docker compose -f /opt/rada/docker-compose.ncp.yml ps` (3개 healthy) |
| Cloud DB 운영중 | NCP 콘솔 상태 "운영중" |
| Spring API 외부 접근 | 발표 PC 에서 `curl http://223.130.154.165:8080/api/metrics` → 401 정상 |
| Grafana 접속 | 발표 PC 에서 `http://223.130.154.165:3000` → 로그인 페이지 |
| 40 PC 데이터 흐름 | SQL: 모든 PC 의 age 5~10초 이내 |
| 발표 자료 출처 | `docs/fp_field_analysis_ncp.md` 의 표/SQL 인용 |

---

## 7. 발표 끝난 후 (운영 종료)

| 시나리오 | 절차 |
|---|---|
| **잠시 중단, 나중에 재개** | NCP 콘솔에서 App VM + Cloud DB "정지" → 디스크 보존료만 부과 |
| **완전 종료, 데이터 백업** | `pg_dump` 으로 metrics_history / anomaly_history 추출 → 그 후 NCP 리소스 반납 |
| **학생 PC 정리** | 마에스트로 새 이미지에 RADA 제거된 상태로 저장 (선택) — 또는 그대로 두고 운영 종료 |

### 7-1. 데이터 백업 명령 (필요 시)

```bash
# NCP VM SSH 에서
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
  --table=pc_monitor.metrics_history \
  --table=pc_monitor.anomaly_history \
  --table=pc_monitor.ai_judgment_history \
  --table=pc_monitor.pc_info \
  > /tmp/rada-backup.sql

# 본인 PC 로 복사 (scp 가능하면)
# 또는 cat 후 복붙
```

---

## 8. 체크리스트

### 학교 도착 후

- [ ] 학교 외부 IP 확인 (`ifconfig.me`)
- [ ] NCP ACG 에 학내 CIDR 추가 (3000, 선택 22)
- [ ] Cloud DB 30GB 확장
- [ ] 학교 PC 에서 Grafana 접속 검증

### 배포 시작 (실습실)

- [ ] USB / D: 에 RADA-deploy 폴더 복사
- [ ] PC 1대 시범 → install.bat → 정지 → 이미지 저장 → 절차 익숙해진 후
- [ ] 나머지 39대 순차 배포 (PC 번호 라벨 따라)

### 배포 후 즉시

- [ ] NCP SQL 로 40 PC 모두 들어오는지 확인
- [ ] keys.csv 모두 폐기 (USB / D: / 학생 PC 등 모든 위치)
- [ ] long-run 누적 시작 (그냥 두면 됨)

### 발표 전

- [ ] §6 점검 항목 모두 통과
- [ ] 발표 자료 인용 데이터 최신 SQL 결과로 갱신

---

## 참고 — 진행 상황 (2026-05-25 기준)

| 작업 | 상태 |
|---|---|
| NCP 인프라 (VPC + ACG + Cloud DB + App VM) | ✅ |
| Docker 스택 (Spring + ML + Grafana) | ✅ |
| Flyway migration V1~V8 | ✅ |
| 클라이언트 PyInstaller 빌드 + Task Scheduler | ✅ |
| cmd 깜빡임 패치 (subprocess no-window) | ✅ |
| 정상 사용 FP 검증 (7h39m / 0건) | ✅ |
| Fast-path + Stealth mining trigger 검증 | ✅ |
| API key 40개 발급 | ✅ |
| install.bat + README.txt 배포 패키지 | ✅ |
| Retention crontab (14일/90일) | ✅ |
| Cloud DB 30GB 확장 | ⬜ |
| 학내망 Grafana 허용 (3000) | ⬜ |
| 학생 PC 40대 배포 | ⬜ |
| AI agent 활성화 | ⬜ |
| Grafana 패널 미화 | ⬜ |
| 2주 long-run 누적 | ⬜ |
