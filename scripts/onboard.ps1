#requires -Version 5.1
<#
.SYNOPSIS
  RADA dev 환경 1-step 온보딩.

.DESCRIPTION
  1) .env 가 없으면 .env.example 복사
  2) docker compose up -d --build
  3) compose ps 로 healthy 확인 (timeout 90s)
  4) demo seed 적용 (PC-01~40 + pc-smoke)
  5) anomaly_trigger.py 한 발 → smoke
  6) Grafana 접속 안내 출력

.EXAMPLE
  pwsh -File scripts/onboard.ps1
#>

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($n, $msg) { Write-Host "`n[$n/6] $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Fail($msg, $next) {
    Write-Host "  FAIL  $msg" -ForegroundColor Red
    Write-Host "        다음 단계: $next" -ForegroundColor Yellow
    exit 1
}

# ---- 1) .env ----
Step 1 ".env 준비"
if (-not (Test-Path .env)) {
    if (-not (Test-Path .env.example)) { Fail ".env.example 파일이 없음" "git pull 또는 저장소 상태 확인" }
    Copy-Item .env.example .env
    Ok ".env.example -> .env 복사"
} else {
    Ok ".env 이미 존재 (그대로 사용)"
}

# ---- 2) docker compose up ----
Step 2 "docker compose up -d --build"
try {
    docker compose up -d --build | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "compose up exited $LASTEXITCODE" }
    Ok "컨테이너 기동 시작"
} catch {
    Fail "docker compose up 실패: $_" "Docker Desktop 실행 여부 확인, 'docker compose logs' 로 원인 추적"
}

# ---- 3) healthy wait ----
Step 3 "서비스 healthy 대기 (최대 90초)"
$deadline = (Get-Date).AddSeconds(90)
$expected = @('postgres', 'ml-server', 'spring-server', 'grafana')
$ready = $false
while ((Get-Date) -lt $deadline) {
    $psJson = docker compose ps --format json 2>$null
    if ($LASTEXITCODE -eq 0 -and $psJson) {
        # compose v2 may emit JSON-lines; normalize
        $services = @()
        foreach ($line in ($psJson -split "`n")) {
            $line = $line.Trim()
            if (-not $line) { continue }
            try { $services += ($line | ConvertFrom-Json) } catch {}
        }
        $running = $services | Where-Object { $_.State -eq 'running' -or $_.Health -eq 'healthy' -or $_.Status -like '*Up*' }
        if ($running.Count -ge $expected.Count) { $ready = $true; break }
    }
    Start-Sleep -Seconds 3
}
if ($ready) {
    Ok "모든 컨테이너 running"
} else {
    Write-Host "  WARN  90초 안에 모든 서비스 healthy 확인 못함 — 계속 진행하지만 'docker compose ps' 직접 확인 권장" -ForegroundColor Yellow
}

# ---- 4) demo seed ----
Step 4 "demo seed 적용"
if (-not (Test-Path "infra/seed/demo_data.sql")) {
    Fail "infra/seed/demo_data.sql 없음" "저장소 상태 확인"
}
try {
    $sql = Get-Content -Raw infra/seed/demo_data.sql
    $sql | docker compose exec -T postgres psql -U rada -d pc_monitor | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "psql exited $LASTEXITCODE" }
    Ok "PC-01~40 + pc-smoke 시드 적용"
} catch {
    Fail "seed 적용 실패: $_" "'docker compose logs postgres' 확인, postgres 컨테이너 healthy 상태 확인"
}

# ---- 5) smoke test ----
Step 5 "anomaly_trigger smoke (pc-smoke, HIGH 누적 확인)"
if (-not (Test-Path "tools/anomaly_trigger.py")) {
    Fail "tools/anomaly_trigger.py 없음" "저장소 상태 확인"
}
try {
    python tools/anomaly_trigger.py | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "anomaly_trigger exited $LASTEXITCODE" }
    Ok "smoke 통과"
} catch {
    Fail "smoke 실패: $_" "'docker compose logs spring-server ml-server' 확인. API_KEY_PEPPER 가 dev 기본값인지 점검"
}

# ---- 6) 안내 ----
Step 6 "완료"
Write-Host @"

  RADA dev 환경 준비 완료.

  Grafana       : http://localhost:3000  (admin / admin)
  Spring health : http://localhost:8080/actuator/health
  ML status     : http://localhost:8000/status

  다음 단계:
    - 클라이언트 별도 기동: python client.py
    - 회귀 테스트: pytest    (목표 282 PASS)
                  cd server-spring; .\gradlew test --tests "*Test"  (목표 77 PASS)
    - 기여 방법: CONTRIBUTING.md 참조

"@ -ForegroundColor Green
