@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title NightDiary Start

echo ==========================================
echo    NightDiary V2  Start
echo ==========================================
echo.

echo Starting backend (port 8000)...
start "NightDiary-Backend" powershell -NoExit -Command "Set-Location '%~dp0server'; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

echo Starting frontend (port 5173)...
start "NightDiary-Frontend" powershell -NoExit -Command "Set-Location '%~dp0'; npm run dev"

echo.
echo ==========================================
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo ==========================================
echo.
echo  Close windows to stop services.
echo  Opening browser in 5 seconds...
timeout /t 5 /nobreak >nul

start http://localhost:5173
exit
