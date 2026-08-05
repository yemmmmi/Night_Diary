# 夜记 NightDiary V2 一键启动脚本
# 双击 start.ps1 或在 PowerShell 中运行 ./start.ps1

$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "       YeJi NightDiary V2  Start" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 0. Load .env file (so child processes inherit DATABASE_URL etc.)
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Write-Host "[0/2] Loading .env..." -ForegroundColor Yellow
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split '=', 2
            if ($parts.Length -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim().Trim('"').Trim("'")
                Set-Item -Path "Env:$key" -Value $value
            }
        }
    }
    Write-Host "      .env loaded" -ForegroundColor Green
} else {
    Write-Host "[0/2] No .env found, using defaults (SQLite)" -ForegroundColor DarkGray
}

# 1. Start backend
Write-Host "[1/2] Starting backend (port 8000)..." -ForegroundColor Yellow
$backendCmd = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory "$ProjectRoot\server" `
    -PassThru `
    -WindowStyle Normal

# Wait for backend health
Write-Host "      Waiting for backend..." -NoNewline
$backendReady = $false
for ($i = 1; $i -le 40; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {}
    Write-Host "." -NoNewline
}
if ($backendReady) {
    Write-Host " OK!" -ForegroundColor Green
} else {
    Write-Host " TIMEOUT (continuing anyway)" -ForegroundColor Red
}

# 2. Start frontend
Write-Host "[2/2] Starting frontend (port 5173)..." -ForegroundColor Yellow
$frontendCmd = Start-Process -FilePath "cmd" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory $ProjectRoot `
    -PassThru `
    -WindowStyle Normal

# Wait for frontend
Write-Host "      Waiting for frontend..." -NoNewline
for ($i = 1; $i -le 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            break
        }
    } catch {}
    Write-Host "." -NoNewline
}
Write-Host " OK!" -ForegroundColor Green

# Done
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Started!" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Close the backend/frontend windows to stop." -ForegroundColor Gray
Write-Host ""

Start-Process "http://localhost:5173"
