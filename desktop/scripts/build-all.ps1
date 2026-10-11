# 一键：前端构建 → Python 运行时 → Electron 编译 → NSIS 打包
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = Split-Path -Parent $here
$repo = Split-Path -Parent $desktop

Write-Host '== 1/4 build frontend =='
Push-Location $repo; npm run build; Pop-Location

Write-Host '== 2/4 build python runtime =='
& (Join-Path $here 'build-runtime.ps1')

Write-Host '== 3/4 compile electron host =='
Push-Location $desktop; npm run build; Pop-Location

Write-Host '== 4/4 package NSIS installer =='
Push-Location $desktop
npx electron-builder --win nsis --config electron-builder.yml --publish never
Pop-Location

Write-Host '== done: desktop/release/NightDiary-*-setup.exe =='