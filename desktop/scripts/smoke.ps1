# 开发态冒烟：构建前端 + 编译 Electron 宿主 + 用本地 venv 起后端并打开窗口。
# 人工确认：窗口打开后能登录、能新建一篇日记。
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = Split-Path -Parent $here
$repo = Split-Path -Parent $desktop

# 1) 构建前端（产出 dist/，由后端静态托管）
Push-Location $repo
npm run build
Pop-Location

# 2) 编译 Electron 宿主
Push-Location $desktop
npm run build

# 3) 指向本地 venv 的 python，启动 Electron（main 会 spawn 后端并开窗）
$env:NIGHT_DIARY_PYTHON = Join-Path $repo 'server\.venv\Scripts\python.exe'
npx electron .
Pop-Location