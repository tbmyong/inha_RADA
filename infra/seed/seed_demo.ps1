# RADA demo seed runner (Windows PowerShell). DEV ONLY.
# Pipes infra/seed/demo_data.sql into the postgres container.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$sql  = Join-Path $here 'demo_data.sql'
Write-Host "Seeding demo data from $sql"
Get-Content -Raw -Encoding UTF8 $sql | docker compose exec -T postgres psql -U rada -d pc_monitor -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) { throw "Seed failed (exit $LASTEXITCODE)" }
Write-Host "Seed OK."
