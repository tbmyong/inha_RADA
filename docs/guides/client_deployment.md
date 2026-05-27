# 클라이언트 배포 — PyInstaller + Task Scheduler

> **이전 단계**: [`ncp_deployment.md`](ncp_deployment.md) (NCP 서버 운영 중)
> **다음 단계**: [`deployment_checklist.md`](deployment_checklist.md) (실제 학생 PC 40대 배포 체크리스트)

학생 PC 40대에 RADA client 를 백그라운드 자동 시작 + 마에스트로 이미지 baseline 으로 동결하는 절차.

## 작업 순서 (이 문서의 흐름)

```
Phase 1   PyInstaller 빌드 (개발자 PC, 1회)         ~10분
Phase 2   본인 PC 시범 — install.bat 검증           ~15분
Phase 3   학생 PC 40대 API key 발급                ~5분
Phase 4   배포 패키지 구성                          ~5분
Phase 5   학생 PC 배포 (실습실 — 마에스트로 case A) ~40분
Phase 6   배포 후 검증 + 보안 정리                  ~10분
```

총 약 1시간 25분.

---

## Phase 1 — PyInstaller 빌드 (개발자 PC, 1회)

### 1-1. 빌드

본인 PC PowerShell:

```powershell
cd C:\Users\admin\Desktop\rada
git pull
pip install pyinstaller

# 이전 빌드 정리 (있으면)
Remove-Item -Recurse -Force dist, build, rada_client.spec -ErrorAction SilentlyContinue

pyinstaller --onefile --noconsole `
  --name rada_client `
  --hidden-import pynvml `
  --hidden-import GPUtil `
  --collect-all client_core `
  client.py
```

빌드 5~10분 소요. 결과: `dist\rada_client.exe` (약 22 MB).

### 1-2. 빌드 옵션 의미

| 옵션 | 효과 |
|---|---|
| `--onefile` | 단일 exe 로 압축 (Python 인터프리터 + 모든 의존성 통째로) |
| `--noconsole` | 실행 시 cmd 창 안 뜸 (= pythonw 효과) |
| `--hidden-import pynvml/GPUtil` | 동적 import 라 PyInstaller 자동 추적 실패 → 명시 |
| `--collect-all client_core` | `client_core/` 패키지 트리 전체 포함 |

### 1-3. 빌드 검증 — 본인 PC 에서

```powershell
(Get-Item dist\rada_client.exe).LastWriteTime
(Get-Item dist\rada_client.exe).Length / 1MB
```

→ 빌드 시각이 방금, 크기 20~40 MB 면 정상.

### 1-4. 빌드 함정

| 함정 | 증상 | 해결 |
|---|---|---|
| `client_core` not a package WARNING | 빌드 로그에 경고 | 무해 — `--collect-all` 가 코드는 모두 포함. data 파일이 없는 경우 |
| pynvml deprecated FutureWarning | 노란 경고 | 무해 — 로컬 빌드 환경 알림. exe 동작 무관 |
| **5초마다 cmd 창 깜빡임** | exe 실행 시 학생 PC 화면에 깜빡거림 | ★ 본 repo 의 `client_core/__init__.py` 가 subprocess `CREATE_NO_WINDOW` 자동 주입. 만약 학생 PC 에서 여전히 깜빡이면 빌드한 exe 가 최신 commit (`6412001`) 이전 버전 — 재빌드 |
| `git pull` 안 함 | 옛 commit 기반 빌드 | 빌드 전 반드시 `git pull` |

---

## Phase 2 — 본인 PC 시범 설치

학생 PC 가기 전 본인 PC 에서 install.bat 전체 흐름을 한 번 검증. **이 단계 통과해야 학생 PC 배포 안전.**

### 2-1. 기존 dev/PC 클라이언트 정지 (있으면)

이미 본인 PC 에서 `python client.py` 또는 다른 버전 돌고 있다면 정리:

```powershell
# 관리자 PowerShell
schtasks /End /TN "RADA Client" 2>$null
Get-Process rada_client -EA SilentlyContinue | Stop-Process -Force
Get-Process python -EA SilentlyContinue | Where-Object { $_.MainModule.FileName -like "*client.py*" } | Stop-Process -Force
```

### 2-2. install.bat 시범 실행

(Phase 4 에서 만든 RADA-deploy 폴더 있다는 가정 — 처음이면 Phase 3 / 4 먼저 진행)

```powershell
cd C:\Users\admin\Desktop\RADA-deploy
.\install.bat
```

> ⚠ **관리자 권한 필수** — install.bat 가 `C:\ProgramData\` 쓰기, Task Scheduler `/RL HIGHEST` 등록.
> 일반 PowerShell 이면 `Run as Administrator` 에러 뜸. **시작 메뉴에서 PowerShell 우클릭 → 관리자 권한** 으로 새로 켜기.

프롬프트 → 본인 PC 의 테스트 번호 (`01`) 입력 → Enter.

기대 출력:
```
[INFO] Installing PC-01 ...
SUCCESS: The scheduled task "RADA Client" has been created.
[OK] PC-01 installed and running in background.
```

### 2-3. 동작 검증

```powershell
# 프로세스
Get-Process rada_client
# → 2개 프로세스 (런처 + 본체)

# Task 상태
schtasks /Query /TN "RADA Client" /V /FO LIST | findstr /C:"Status" /C:"Schedule Type" /C:"Last Result"
# Schedule Type: At logon time
# Status: Running
# Last Result: 0
```

NCP VM 에서:
```bash
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT MAX(collected_at), now() - MAX(collected_at) AS age FROM pc_monitor.metrics_history WHERE pc_id='PC-01';"
# age 5~10초 이내
```

### 2-4. 자동 시작 검증 (재부팅)

가장 결정적인 검증. **건너뛰면 안 됨**:

```powershell
Get-Process rada_client | Select-Object Id
# → 이전 PID 메모
shutdown /r /t 0
```

재부팅 → 로그인 → 30초 대기 후:
```powershell
Get-Process rada_client | Select-Object Id
# → 새로운 PID 두 개 자동으로 떠있으면 ONLOGON 트리거 정상
```

NCP 에서 age 가 다시 5~10초 이내로 돌아오면 → **자동 시작 완벽 동작**, 학생 PC 배포 안전.

### 2-5. 본인 PC 시범 함정

| 함정 | 증상 | 해결 |
|---|---|---|
| `schtasks /End` 가 access denied | 일반 권한 PS | 관리자 PS 로 다시 |
| `Stop-Process` access denied | Task 가 `/RL HIGHEST` 로 떴음 | 관리자 PS 로 다시 |
| `copy /Y` 가 PowerShell 에서 에러 | cmd 문법 | `Copy-Item -Force` 사용 |
| 5초마다 cmd 창 깜빡임 | 옛 exe (commit `6412001` 이전) | Phase 1 재빌드 |
| install.bat 한글 깨짐 (`???`) | ASCII 인코딩 한계 | 본 repo 의 install.bat 은 영어 메시지로 작성됨 — 정상 |

---

## Phase 3 — 학생 PC 40대 API key 발급

NCP VM SSH 에서:

```bash
cd /opt/rada
set -a; source .env; set +a

python3 tools/provision_pcs.py \
  --count 40 --prefix PC \
  --output /tmp/student_keys.csv \
  --yes \
  --db-url "postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
```

> `--yes` 옵션: 같은 pc_id 가 이미 DB 에 있으면 api_key 회전 (덮어쓰기). 처음이면 무관, 재발급 시 필요.

### 검증

```bash
# CSV 41줄 (헤더 + 40)
wc -l /tmp/student_keys.csv

# CSV 와 DB hash 매칭
head -3 /tmp/student_keys.csv
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT pc_id, substring(api_key, 1, 16) AS hash_prefix
FROM pc_monitor.pc_info WHERE pc_id LIKE 'PC-%' ORDER BY pc_id LIMIT 3;"
# CSV 의 hashed_key 앞 16자 == DB 의 hash_prefix 매칭 확인
```

### 본인 PC 로 CSV 가져오기

#### 방법 A — SCP (.pem 키 인증 됐을 때)

본인 PC PowerShell:
```powershell
scp -i C:\Users\admin\Desktop\radaki\rada-key.pem `
  root@<Public IP>:/tmp/student_keys.csv `
  C:\Users\admin\Desktop\
```

#### 방법 B — cat 후 복붙 (키 인증 깨졌을 때 — 가장 확실)

VM SSH 에서:
```bash
cat /tmp/student_keys.csv
```

→ 41줄 출력. PowerShell 에서 **헤더부터 마지막 PC-40 까지 전체 마우스 드래그 → 복사** → 메모장 → **다른 이름으로 저장**:
- 파일: `C:\Users\admin\Desktop\student_keys.csv`
- 인코딩: **UTF-8**
- 파일 형식: **모든 파일 (\*.\*)**

확인:
```powershell
(Get-Content C:\Users\admin\Desktop\student_keys.csv).Count
# → 41 (또는 40 — 헤더 빠뜨려도 install.bat 동작은 무관)
Get-Content C:\Users\admin\Desktop\student_keys.csv -TotalCount 3
```

### Phase 3 함정

| 함정 | 증상 | 해결 |
|---|---|---|
| `set -a; source .env; set +a` 안 함 | provision 이 `DB_HOST` 못 찾음 | source 먼저, 또는 `~/.bashrc` 에 자동 로드 등록 |
| `psycopg2` 미설치 | "service postgres is not running" 에러 (compose 모드 폴백) | `apt install python3-psycopg2` 또는 `pip3 install --break-system-packages psycopg2-binary` |
| `--yes` 빠뜨림 | 회전 시 `Proceed? [y/N]` 에서 abort | `--yes` 명시 |
| Excel 로 csv 열어서 저장 | `=` 시작 raw_key 가 수식으로 변환됨 | 메모장 / VS Code 로만 편집 |
| CSV 헤더 없음 | install.bat 에 영향 없음 (PC-XX 패턴 매칭) | 무시 |
| DB ↔ CSV 키 mismatch | install 후 401 인증 실패 | 재발급 시점이 다르면 발생 — `--yes` 회전 후 즉시 CSV 재복사 |

### VM 정리

CSV 복사 끝나면 즉시:
```bash
shred -u /tmp/student_keys.csv
```

---

## Phase 4 — 배포 패키지 구성

본인 PC PowerShell:

```powershell
$DEPLOY = "C:\Users\admin\Desktop\RADA-deploy"
mkdir -Force $DEPLOY | Out-Null

# 1) exe 복사
Copy-Item -Force C:\Users\admin\Desktop\rada\dist\rada_client.exe $DEPLOY\

# 2) keys.csv
Copy-Item -Force C:\Users\admin\Desktop\student_keys.csv $DEPLOY\keys.csv
```

### 4-1. install.bat 생성

```powershell
$bat = @'
@echo off
setlocal enabledelayedexpansion

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERR] Run as Administrator.
    pause
    exit /b 1
)

REM SRC = directory of this .bat (trailing backslash). Quote everywhere so
REM paths with spaces (OneDrive Desktop, "바탕 화면", 한글 폴더) work.
set "SRC=%~dp0"

set /p PC_NUM="Enter PC number (e.g. 01 / 02 / ... / 40): "
set "PC_ID=PC-%PC_NUM%"

set "RAW_KEY="
for /f "usebackq tokens=1,2 delims=," %%a in ("%SRC%keys.csv") do (
    if "%%a"=="!PC_ID!" set "RAW_KEY=%%b"
)

if "!RAW_KEY!"=="" (
    echo [ERR] PC_ID "!PC_ID!" not found in keys.csv.
    pause
    exit /b 1
)

echo [INFO] Installing !PC_ID! ...

if not exist "C:\ProgramData\RADA" mkdir "C:\ProgramData\RADA"
if not exist "%APPDATA%\rada" mkdir "%APPDATA%\rada"

copy /Y "%SRC%rada_client.exe" "C:\ProgramData\RADA\" >nul

(
echo mode: springboot
echo spring_boot_url: http://223.130.154.165:8080/api/metrics
echo api_key: !RAW_KEY!
echo interval: 5
) > "%APPDATA%\rada\config.yaml"

schtasks /Create /TN "RADA Client" /TR "C:\ProgramData\RADA\rada_client.exe" /SC ONLOGON /RL HIGHEST /F >nul
schtasks /Run /TN "RADA Client" >nul

REM PyInstaller --onefile first-extract takes 5~10s. Wait longer than 3s.
timeout /t 8 /nobreak >nul
tasklist | findstr /i rada_client >nul && (
    echo [OK] !PC_ID! running in background.
) || (
    echo [INFO] Task scheduled. exe may still be extracting ^(PyInstaller onefile^).
    echo        Check in 30 sec: tasklist ^| findstr rada_client
)

echo.
pause
'@

Set-Content -Encoding ASCII -Path "$DEPLOY\install.bat" -Value $bat
```

> ⚠ **install.bat 의 `spring_boot_url`** — 실제 NCP Public IP 로 바꿨는지 확인. 위 예시는 `223.130.154.165` 이지만 본인 NCP IP 가 다르면 수정 필요.
>
> ⚠ **OneDrive 데스크탑 / 한글 폴더 경로 함정** — 학생 PC 가 OneDrive 데스크탑 (`C:\Users\<user>\OneDrive\바탕 화면\`) 을 쓰면 폴더 경로에 공백이 들어가 cmd 가 잘못 파싱. 위 템플릿은 `set "SRC=%~dp0"` + `usebackq` + 따옴표 처리로 공백 / 한글 경로 모두 지원. 옛 버전 (3초 대기 + 따옴표 없음) 은 OneDrive 환경에서 "파일 ... 바탕을(를) 찾을 수 없습니다" 에러 발생함.

### 4-2. README.txt — 작업자용 운영 매뉴얼

배포 패키지 안에 작업 절차를 같이 두면 실습실에서 헷갈리지 않음:

```powershell
$readme = @"
=== RADA Client 실습실 배포 절차 (마에스트로 case A) ===

[PC 1대 작업 — 약 1분]
1. install.bat 우클릭 → 관리자 권한 실행
2. PC 번호 입력 (01, 02, ... 40)
3. [OK] 메시지 확인
4. 작업관리자에서 rada_client.exe 두 개 떠있는지 확인
5. 클라이언트 정지 (이미지 깨끗하게):
     schtasks /End /TN "RADA Client"
     taskkill /F /IM rada_client.exe
6. 마에스트로 baseline 이미지 저장
7. 다음 PC

[이미지 복원 후]
부팅 → 학생 로그인 → Task Scheduler 가 자동 실행 → 5초마다 NCP 로 metric

[보안] keys.csv 는 평문 raw_key 포함. 배포 끝나면 USB / D 드라이브에서 삭제.
"@

Set-Content -Encoding UTF8 -Path $DEPLOY\README.txt -Value $readme
```

### 4-3. 패키지 확인

```powershell
dir $DEPLOY
```

기대:
```
install.bat       ~1.2 KB
keys.csv          ~5 KB
rada_client.exe   ~22 MB
README.txt        ~700 bytes
```

### 4-4. (선택) USB / 공유폴더로 옮기기

```powershell
# USB (E: 가정)
Copy-Item -Recurse $DEPLOY E:\

# D 드라이브에 복사 (학생 PC 작업 시 빠른 접근)
mkdir -Force D:\RADA-deploy | Out-Null
Copy-Item -Force $DEPLOY\* D:\RADA-deploy\
```

---

## Phase 5 — 학생 PC 배포 (실습실)

### 5-1. 사전 확인 — 마에스트로 케이스 판별

| 케이스 | 설명 | 본 절차 적용 |
|---|---|---|
| **A** — PC 별 자기 이미지 보관 + 부팅 시 자기 이미지로 복원 | 가장 흔함 | ✅ 적합 |
| **B** — 마스터 이미지 1개 → 40 클론 | 모든 PC 가 같은 api_key 가지게 됨 | ❌ 별도 first-boot provisioning 필요 |

> 모르면 IT 담당자에게 "PC 별로 이미지를 각각 만들었나요?" 질문. A 가 정답이면 그대로 진행.

### 5-2. PC 1대 표준 절차 (1분)

1. USB 꽂거나 D:\RADA-deploy 열기
2. **install.bat 우클릭 → 관리자 권한 실행**
3. UAC 확인 → 예
4. `Enter PC number` → 해당 PC 번호 (책상/모니터 라벨) 입력
5. `[OK] PC-XX installed and running in background.` 메시지 확인
6. 작업관리자 (Ctrl+Shift+Esc) → 세부정보 탭 → `rada_client.exe` 2개 떠있는지 확인
7. **클라이언트 정지** (이미지 저장 직전):
   ```cmd
   schtasks /End /TN "RADA Client"
   taskkill /F /IM rada_client.exe
   ```
   작업관리자에서 `rada_client.exe` 사라진 것 확인
8. **마에스트로로 baseline 이미지 저장** (평소 절차)
9. 다음 PC 로 이동

### 5-3. 왜 정지 후 이미지 저장하나

| 이유 | 설명 |
|---|---|
| 깨끗한 디스크 상태 | local_queue.jsonl 같은 중간 파일 안 만들어진 상태 |
| 로그 절단 위험 없음 | 쓰기 중인 로그 잘림 방지 |
| 메모리/캐시 무관 | 마에스트로는 디스크 이미지 — 메모리 영향 0 |
| baseline 안정성 | 학생이 client 망가뜨려도 이미지 복원 시 깨끗한 상태 |

> **Task Scheduler 등록 정보는 그대로 유지** (`/Delete` 아니라 `/End` 만 함). 다음 부팅 시 ONLOGON 으로 자동 시작.

### 5-4. 이미지 복원 후 동작

```
[이미지 복원 부팅]
  ↓
[학생 로그인]
  ↓
Task Scheduler "RADA Client" 가 ONLOGON 트리거로 자동 실행
  ↓
C:\ProgramData\RADA\rada_client.exe 백그라운드 시작
  ↓
%APPDATA%\rada\config.yaml 의 api_key 로 NCP 로 metric 송신
```

학생은 아무것도 안 만지고 화면에 아무것도 안 뜸.

### 5-5. Phase 5 함정

| 함정 | 증상 | 해결 |
|---|---|---|
| install.bat 일반 권한 실행 | `[ERR] Run as Administrator` | 우클릭 → 관리자 권한 |
| keys.csv 가 없는 폴더에서 실행 | `[ERR] PC_ID PC-XX not found` | install.bat 와 keys.csv 같은 폴더에 있어야 함 |
| PC 번호 자릿수 | `1` 입력 시 `PC-1` 검색 → 못 찾음 | `01` 두 자리로 입력 |
| 학생 PC 방화벽이 8080 차단 | install 직후 데이터 안 들어옴 | 학내 네트워크 관리자에게 outbound 8080 허용 협의 |
| 마에스트로 case B 였음 | 모든 PC 가 PC-01 처럼 보임 | 별도 first-boot 스크립트 필요 (현 매뉴얼 부적합) |

---

## Phase 6 — 배포 후 검증 + 보안 정리

### 6-1. NCP 에서 40 PC 흐름 확인

```bash
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT pc_id, MAX(collected_at) AS last, now() - MAX(collected_at) AS age
FROM pc_monitor.metrics_history WHERE pc_id LIKE 'PC-%'
GROUP BY pc_id ORDER BY pc_id;"
```

기대: 40 행, 각 age 5~10초 이내.

PC 절전/꺼짐 상태면 그 PC 만 age 길거나 행 없음.

### 6-2. Grafana 에서 시각화 확인

브라우저 `http://<NCP Public IP>:3000` → Dashboards → RADA → `rada-main`
- 40대 honeycomb 셀 채워짐
- CPU/GPU/네트워크 패널 데이터 흐름

### 6-3. 보안 정리

```powershell
# 본인 PC
Remove-Item C:\Users\admin\Desktop\RADA-deploy\keys.csv
Remove-Item C:\Users\admin\Desktop\student_keys.csv

# USB / D 드라이브의 keys.csv 도 삭제
Remove-Item E:\RADA-deploy\keys.csv -EA SilentlyContinue
Remove-Item D:\RADA-deploy\keys.csv -EA SilentlyContinue
```

### 6-4. 학생 PC 의 keys.csv 처리

마에스트로 이미지에 keys.csv 가 포함되면 모든 학생이 raw_key 40개를 보게 됨. **이미지 저장 전에 학생 PC 의 D:\RADA-deploy\ 등에서 삭제**:

```cmd
del D:\RADA-deploy\keys.csv
```

또는 install.bat 작업 시 keys.csv 는 USB 에만 두고 학생 PC 디스크에 복사하지 않는 절차.

---

## 운영 명령 모음 (학생 PC — 관리자 PowerShell)

### 일시 중지 / 시작 / 상태

```powershell
# 일시 중지
schtasks /End /TN "RADA Client"

# 다시 시작
schtasks /Run /TN "RADA Client"

# 상태
schtasks /Query /TN "RADA Client" /V /FO LIST

# 살아있는지
Get-Process rada_client -EA SilentlyContinue
tasklist | findstr rada_client
```

### 완전 제거 — 실제 검증된 순서 (4단계)

> ⚠ **함정**: `schtasks /Delete` 만 한다고 프로세스 / 파일이 같이 사라지지 않음.
> exe 가 실행 중이면 파일 락이 걸려 `Remove-Item` 이 "액세스 거부" 에러로 실패함.
> 반드시 **Task 정지 → 프로세스 kill → 파일 삭제** 순서.

```powershell
# 1. Task 정지 + 삭제
schtasks /End    /TN "RADA Client" 2>$null
schtasks /Delete /TN "RADA Client" /F 2>$null
schtasks /Delete /TN "RADA Watchdog" /F 2>$null

# 2. 실행 중인 프로세스 강제 종료 (파일 락 해제)
taskkill /F /IM rada_client.exe 2>$null
Start-Sleep 3
Get-Process rada_client -EA SilentlyContinue
# → 출력 없어야 다음 단계 진행

# 3. 파일 + 설정 삭제
Remove-Item -Recurse -Force C:\ProgramData\RADA  -EA SilentlyContinue
Remove-Item -Recurse -Force "$env:APPDATA\rada" -EA SilentlyContinue

# 4. 검증 (네 줄 모두 False / 비어있어야 함)
Test-Path C:\ProgramData\RADA       # False
Test-Path "$env:APPDATA\rada"       # False
schtasks /Query | findstr /i rada   # (출력 없음)
Get-Process rada_client -EA SilentlyContinue   # (출력 없음)
```

`Test-Path` 가 False 두 번 + findstr / Get-Process 출력 0 이면 완전 제거 성공.

## (선택) Watchdog — 5분 단위 자동 부활

학생이 작업관리자에서 죽이거나 크래시 시 5분 내 복구:

```powershell
schtasks /Create /TN "RADA Watchdog" `
  /TR "powershell -NoProfile -WindowStyle Hidden -Command \"if (-not (Get-Process rada_client -EA SilentlyContinue)) { Start-Process 'C:\ProgramData\RADA\rada_client.exe' -WindowStyle Hidden }\"" `
  /SC MINUTE /MO 5 /RL HIGHEST /F
```

지금 단계엔 필수 아님. ONLOGON 만으로도 학기 운영 충분.

---

## 자주 부딪힌 함정 모음 (요약)

| 함정 | 단계 | 해결 |
|---|---|---|
| `--collect-all client_core` 경고 | Phase 1 | 무해 (data 파일 없어서) |
| 5초마다 cmd 깜빡임 | Phase 1 | `client_core/__init__.py` 의 CREATE_NO_WINDOW 패치 포함 commit 이후 빌드 |
| `Run as Administrator` 에러 | Phase 2/5 | 관리자 PowerShell 또는 install.bat 우클릭 → 관리자 권한 |
| `copy /Y` vs `Copy-Item -Force` | Phase 4 | PowerShell 은 `Copy-Item -Force` 또는 `cmd /c copy /Y` |
| Stop-Process access denied | Phase 2 | 관리자 PS 필수 (Task `/RL HIGHEST`) |
| install.bat 한글 깨짐 | Phase 4 | ASCII 인코딩으로 작성, 영어 메시지 |
| `set /p` 괄호 안 `)` 가 닫힘으로 해석 | Phase 4 | `^` 로 escape (위 install.bat 에 적용됨) |
| PC 번호 자릿수 | Phase 5 | `01` (2자리). `1` 단독은 못 찾음 |
| keys.csv Excel 손상 | Phase 3 | Excel 로 저장 절대 X. 메모장만 |
| Maestro case B | Phase 5 | 본 매뉴얼 부적합. 별도 first-boot provisioning 설계 필요 |
| **"파일 ... 바탕을(를) 찾을 수 없습니다"** | Phase 5 | OneDrive 데스크탑 경로 (`...OneDrive\바탕 화면\`) 공백 파싱 실패. 위 install.bat 템플릿이 `set "SRC=%~dp0"` + `usebackq` + 따옴표 처리로 해결. 옛 install.bat 쓰면 발생. |
| **install.bat 의 [WARN] Process not found** | Phase 5 | 3초 대기가 PyInstaller `--onefile` 첫 압축해제 시간보다 짧아서. **대부분 정상** — 30초 후 `tasklist \| findstr rada_client` 또는 NCP DB 의 age 5~10초 확인하면 살아있음. 최신 install.bat 은 8초 대기 + 더 명확한 [INFO] 메시지. |
| **`Remove-Item exe` 액세스 거부** | 운영 | 프로세스 실행 중이라 파일 락. 반드시 `taskkill /F` 먼저 → `Start-Sleep 3` → `Remove-Item`. 위 "완전 제거" 4단계 참조. |
| **Task 만 삭제했는데 프로세스 / 파일 남음** | 운영 | `schtasks /Delete` 는 Task 등록만 지움. 프로세스 / 파일은 별개로 정리해야. 위 "완전 제거" 4단계 참조. |

---

## 다음 단계

학생 PC 배포 진행 → **체크리스트** 따라가기:

→ [`deployment_checklist.md`](deployment_checklist.md)

운영 중 코드/대시보드/scoring 변경 시:

→ [`deploy_updates.md`](deploy_updates.md)

## 참고

- [`ncp_deployment.md`](ncp_deployment.md) — NCP 서버 셋업 (선행)
- [`pc-provisioning.md`](../reference/pc-provisioning.md) — API key 발급/회전 상세
- [`fp_field_analysis_ncp.md`](../analysis/fp_field_analysis_ncp.md) — NCP 환경 검증 결과
- `client_core/README.md` — 클라이언트 모듈 구조
