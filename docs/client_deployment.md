# RADA Client 배포 매뉴얼 (PyInstaller + Task Scheduler)

학생 PC 40대에 RADA 모니터링 클라이언트를 백그라운드로 자동 실행시키기 위한
표준 배포 절차. 본 문서는 **클라이언트 측 패키징/설치**만 다룬다.

- 서버 측 배포(NCP, docker-compose, Spring, ML, Postgres, Grafana)는 별도 문서.
- API key 발급/회전/폐기는 `docs/pc-provisioning.md` 참조.

전제 — 다음이 모두 끝나있어야 본 절차를 시작할 수 있다:

1. NCP 서버에 RADA 서버 스택이 떠 있고 외부에서 `http://<공인IP>:8080/api/metrics` 가 접근 가능.
2. `tools/provision_pcs.py` 로 학생 PC 수만큼 API key 발급 (`pc_info` 테이블 등록 완료).
3. 학생 PC 에서 위 URL 로 `curl` / ping 이 통한다.

---

## 1. 빌드 (개발자 PC, 1회)

### 1-1. PyInstaller 설치 + 빌드

```powershell
cd C:\Users\admin\Desktop\rada
pip install pyinstaller

pyinstaller --onefile --noconsole `
  --name rada_client `
  --hidden-import pynvml `
  --hidden-import GPUtil `
  --collect-all client_core `
  client.py
```

결과: `dist\rada_client.exe` (25~40 MB)

### 1-2. 빌드 옵션 의미

| 옵션 | 효과 |
|---|---|
| `--onefile` | 의존성 통째로 단일 exe 로 압축 |
| `--noconsole` | 실행 시 cmd 창 안 뜸 (= `pythonw.exe`) |
| `--hidden-import pynvml/GPUtil` | 동적 import 라 PyInstaller 자동 추적 실패 |
| `--collect-all client_core` | `client_core` 패키지 트리 전체 포함 |

### 1-3. 빌드 검증

```powershell
# 개발자 PC 에서 먼저 더블클릭 → 콘솔 안 뜨는지
.\dist\rada_client.exe

# 별도 PowerShell 에서 프로세스 / 전송 확인
tasklist | findstr rada_client
```

서버 측 Grafana 또는 `psql` 로 새 pc_id 가 들어오는지 확인 후 다음 단계.

---

## 2. 배포 패키지 구성

빌드한 exe 옆에 다음 3개 파일을 두고 zip 또는 USB 로 들고 다닌다:

```
RADA-deploy/
├── rada_client.exe        ← §1 산출물
├── config.yaml            ← 서버 주소 + API key (PC 별 또는 공용)
└── install.bat            ← Task Scheduler 등록 스크립트
```

### 2-1. `config.yaml`

PC 별 API key 가 다르면 PC 마다 다른 `config.yaml` 을 가져가야 하고, 공용
키 정책이면 1개로 충분하다 (`provision_pcs.py` 발급 정책에 따라 결정).

```yaml
mode: springboot
spring_boot_url: http://<NCP-공인IP>:8080/api/metrics
api_key: <raw_key>
interval: 5
```

> `pc_id` 는 client 가 hostname 기반으로 자동 생성하므로 따로 지정하지 않는다.

### 2-2. `install.bat`

```bat
@echo off
REM ── RADA Client 설치 (관리자 권한 필수) ──
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERR] 관리자 권한 cmd 또는 PowerShell 에서 실행하세요.
    pause
    exit /b 1
)

REM 1. 디렉터리
if not exist "C:\ProgramData\RADA" mkdir "C:\ProgramData\RADA"
if not exist "%APPDATA%\rada"      mkdir "%APPDATA%\rada"

REM 2. 파일 복사
copy /Y "%~dp0rada_client.exe" "C:\ProgramData\RADA\"   >nul
copy /Y "%~dp0config.yaml"     "%APPDATA%\rada\"        >nul

REM 3. Task Scheduler 등록
schtasks /Create /TN "RADA Client" ^
  /TR "C:\ProgramData\RADA\rada_client.exe" ^
  /SC ONLOGON /RL HIGHEST /F

REM 4. 즉시 1회 실행
schtasks /Run /TN "RADA Client"

echo.
echo [OK] 설치 완료. 다음 로그온부터 자동 시작.
pause
```

`/SC ONLOGON` = 사용자 로그온 시 자동 실행, `/RL HIGHEST` = 관리자 권한
(외부 연결 전체 열람용 — `psutil.net_connections()` 요건).

---

## 3. 학생 PC 배포

### 3-1. 표준 절차 (PC 당 ~30초)

1. USB / 공유폴더로 `RADA-deploy/` 전체 복사
2. `install.bat` 우클릭 → **관리자 권한으로 실행**
3. UAC 확인 → 예
4. `[OK]` 메시지까지 대기 후 창 닫기
5. 다음 PC 로 이동

40대 = 약 20분.

### 3-2. 설치 직후 확인

학생 PC 에서:

```powershell
schtasks /Query /TN "RADA Client" /V /FO LIST | findstr /C:"Status" /C:"Next Run"
tasklist | findstr rada_client
```

서버 (NCP) 에서:

```sql
SELECT DISTINCT pc_id, MAX(collected_at) AS last_seen
FROM pc_monitor.metrics_history
WHERE collected_at > now() - interval '5 minutes'
GROUP BY pc_id
ORDER BY last_seen DESC;
```

---

## 4. 운영 중 관리

| 작업 | 명령 (학생 PC 관리자 cmd) |
|---|---|
| 일시 중지 | `schtasks /End /TN "RADA Client"` |
| 다시 시작 | `schtasks /Run /TN "RADA Client"` |
| 완전 제거 | `schtasks /Delete /TN "RADA Client" /F` 후 폴더 삭제 |
| 코드 업데이트 | 새 `rada_client.exe` 로 덮어쓰기 → Task 재시작 |
| 설정 변경 | `%APPDATA%\rada\config.yaml` 수정 → Task 재시작 |
| 키 회전 | 위 설정 변경과 동일 (raw_key 만 갱신) |

---

## 5. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| 학생 PC 에서 `ModuleNotFoundError` | 빌드 옵션 누락 | `--collect-all client_core` 재빌드 |
| GPU 메트릭이 항상 null | `pynvml` DLL 누락 | `--hidden-import pynvml` 재빌드 |
| `config.yaml not found` | 경로 오타 | `%APPDATA%\rada\config.yaml` 위치 확인 |
| Windows Defender 가 격리 | PyInstaller exe false positive | Defender 예외 등록 또는 코드 서명 |
| 전송 실패 (`401`) | API key 잘못 / pepper 불일치 | `docs/pc-provisioning.md` §인증계약 |
| 전송 실패 (`timeout`) | NCP 보안그룹/방화벽 | 학생 PC → NCP `:8080` outbound 허용 |
| `net_connections()` 일부만 보임 | `/RL HIGHEST` 빠짐 | Task 옵션 재등록 |
| 로그온해도 Task 안 뜸 | Task 비활성/삭제됨 | `schtasks /Query` 로 상태 확인 |

---

## 6. 배포 체크리스트

빌드 / 패키지:
- [ ] `dist\rada_client.exe` 빌드 성공 + 본인 PC 더블클릭에서 무창 실행
- [ ] `config.yaml` 의 `spring_boot_url` 가 학내망에서 reachable
- [ ] `api_key` 가 `pc_info` 테이블에 활성 상태로 존재

배포 직전:
- [ ] 본인 PC 에 `install.bat` 시범 → 로그아웃/로그인 → metric 끊김 없음 30분 관찰
- [ ] Grafana 에서 본인 pc_id 패널이 정상 표시

배포 중:
- [ ] PC 1대마다 `install.bat` 관리자 실행 → `[OK]` 메시지 확인
- [ ] 서버 SQL 로 새 pc_id 들어오는 것 확인

배포 후 (24h):
- [ ] `pc_info` 등록 PC 수 = 실제 metric 송신 PC 수
- [ ] anomaly_history 의 host 별 FP rate 가 기대치 (단일 PC 검증 결과) 와 유사
- [ ] severity 분포에 폭주 패턴 없는지

---

## 7. 보안 / 사생활 주의

- Defender 예외는 **`C:\ProgramData\RADA\rada_client.exe` 경로 한정**으로
  등록. 폴더 전체 예외는 피한다.
- `config.yaml` 의 `api_key` 는 raw 평문이므로 USB / 공유폴더에 둘 때 즉시
  배포 후 삭제. zip 의 경우 비밀번호 보호.
- 본 클라이언트는 사용자 알림 UI 가 없고 사용자 입력/파일을 수집하지 않는다
  (resource metric only). PII 수집 없음.

---

## 참고

- `docs/pc-provisioning.md` — API key 발급/회전
- `docs/team-guide.md` — Fork 워크플로우
- `docs/fp_field_analysis_post_p2.md` — 단일 PC FP 검증 결과 (배포 후 다수
  PC 결과와 비교 기준)
- `client_core/README.md` — 클라이언트 모듈 구조
