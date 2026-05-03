# Smarted launcher — one-shot setup + start.
# Usage:  .\start.ps1
#
# What it does:
#   1. Kills any zombie uvicorn on port 8000
#   2. Activates the venv
#   3. Adds Windows Firewall rule (so the phone can reach :8000) — needs admin once
#   4. Detects your LAN IP and patches lib/services/api_service.dart
#   5. Starts uvicorn (foreground, with --reload, with logs)
#   6. Prints exactly what to run on the phone

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$backend = Join-Path $repo "backend"

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Smarted launcher" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Kill any zombie uvicorn on port 8000
Write-Host "`n[1/5] Killing any process on port 8000..." -ForegroundColor Yellow
$zombies = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
if ($zombies) {
    foreach ($zPid in $zombies) {
        try {
            Stop-Process -Id $zPid -Force -ErrorAction Stop
            Write-Host "      killed PID $zPid" -ForegroundColor Gray
        } catch {}
    }
} else {
    Write-Host "      port 8000 is free" -ForegroundColor Gray
}

# 2. Verify venv exists and activate it
Write-Host "`n[2/5] Activating Python venv..." -ForegroundColor Yellow
$activate = Join-Path $backend ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Host "      ERROR: venv missing at $activate" -ForegroundColor Red
    Write-Host "      Run: cd backend; py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}
. $activate
Write-Host "      venv active" -ForegroundColor Gray

# 3. Detect LAN IP
Write-Host "`n[3/5] Detecting LAN IP..." -ForegroundColor Yellow
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.*" -and
        $_.PrefixOrigin -ne "WellKnown"
    } |
    Select-Object -First 1).IPAddress
if (-not $lanIp) { $lanIp = "127.0.0.1" }
Write-Host "      LAN IP: $lanIp" -ForegroundColor Gray

# 4. Patch the Flutter base URL so the phone can reach this PC
$apiFile = Join-Path $repo "lib\services\api_service.dart"
if (Test-Path $apiFile) {
    $current = Get-Content $apiFile -Raw
    $patched = $current -replace "defaultBaseUrl = 'http://[^']+';", "defaultBaseUrl = 'http://${lanIp}:8000';"
    if ($current -ne $patched) {
        Set-Content -Path $apiFile -Value $patched -NoNewline
        Write-Host "      patched lib/services/api_service.dart -> http://${lanIp}:8000" -ForegroundColor Gray
    } else {
        Write-Host "      api_service.dart already pointing at $lanIp" -ForegroundColor Gray
    }
}

# 5. Add firewall rule (needs admin; we elevate just for this)
Write-Host "`n[4/5] Ensuring Windows Firewall allows port 8000..." -ForegroundColor Yellow
$existing = Get-NetFirewallRule -DisplayName "Smarted Backend" -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "      requesting admin to add the rule (UAC prompt)..." -ForegroundColor Gray
    $cmd = "New-NetFirewallRule -DisplayName 'Smarted Backend' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private,Domain | Out-Null"
    try {
        Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile","-Command",$cmd -Wait
        Write-Host "      firewall rule added" -ForegroundColor Gray
    } catch {
        Write-Host "      WARNING: skipped (you declined UAC). Phone may not reach backend until you accept." -ForegroundColor Yellow
    }
} else {
    Write-Host "      firewall rule already in place" -ForegroundColor Gray
}

# 6. Print phone instructions
Write-Host "`n================================================================" -ForegroundColor Green
Write-Host "  READY" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  On your Pixel 7's Chrome browser, open this to verify reach:" -ForegroundColor White
Write-Host "    http://${lanIp}:8000/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Phone + PC must be on the same Wi-Fi." -ForegroundColor Gray
Write-Host ""
Write-Host "  In ANOTHER terminal, run the Flutter app:" -ForegroundColor White
Write-Host "    cd `"$repo`"" -ForegroundColor Cyan
Write-Host "    flutter run" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend logs follow below. Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host "----------------------------------------------------------------" -ForegroundColor Gray
Write-Host ""

# 7. Start uvicorn (foreground, blocking)
Set-Location $backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
