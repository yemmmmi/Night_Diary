@echo off
chcp 65001 >nul 2>&1
title 夜记 NightDiary - 停止服务

echo ==========================================
echo    夜记 NightDiary V2  停止服务
echo ==========================================
echo.

echo 正在停止后端 (uvicorn)...
taskkill /fi "windowtitle eq 夜记-后端*" /f >nul 2>&1
taskkill /im python.exe /fi "windowtitle eq 夜记-后端*" /f >nul 2>&1

echo 正在停止前端 (vite)...
taskkill /fi "windowtitle eq 夜记-前端*" /f >nul 2>&1
taskkill /im node.exe /fi "windowtitle eq 夜记-前端*" /f >nul 2>&1

echo.
echo 服务已停止。
pause
