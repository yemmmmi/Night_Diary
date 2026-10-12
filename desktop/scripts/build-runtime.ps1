# 构建可重定位的 Python 运行时（python-build-standalone + 依赖），
# 输出到 desktop/resources/runtime，供 electron-builder 作为 extraResources 打包。
# 不使用 PyInstaller —— 目录式运行时规避 onnxruntime/chromadb 的原生依赖冻结问题。
#
# 网络受限环境可用环境变量覆盖镜像：
#   $env:UV_PYTHON_INSTALL_MIRROR = '<python-build-standalone 镜像前缀>'
#   $env:UV_INDEX_URL             = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = Split-Path -Parent $here
$repo = Split-Path -Parent $desktop
$resourcesDir = Join-Path $desktop 'resources'
$runtimeDir = Join-Path $resourcesDir 'runtime'
$stageDir = Join-Path $resourcesDir '.runtime-stage'
$req = Join-Path $desktop 'requirements-runtime.txt'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/"
}

# 0) 默认使用清华 PyPI 镜像（与 Docker 构建保持一致；可用 UV_INDEX_URL 覆盖）
$indexUrl = $env:UV_INDEX_URL
if (-not $indexUrl) { $indexUrl = 'https://pypi.tuna.tsinghua.edu.cn/simple' }

# 1) 安装独立 CPython 到暂存目录（python-build-standalone，可重定位）。
#    uv 会在暂存目录里放一个真实发行版目录（cpython-3.11.x-windows-x86_64-none）
#    外加一个版本 Junction（cpython-3.11-windows-x86_64-none）。为了让
#    python.exe 位于 resources/runtime 根（与 Electron 打包态约定一致），
#    这里先删 Junction，再把真实发行版目录整体搬到 resources/runtime。
Remove-Item $stageDir -Recurse -Force -ErrorAction SilentlyContinue
$env:UV_PYTHON_INSTALL_DIR = $stageDir
uv python install 3.11 --install-dir $stageDir

# Remove-Item 删除 Junction 会抛 NullReference，用 rmdir 更稳。
Get-ChildItem $stageDir -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.LinkType -eq 'Junction' } |
  ForEach-Object { cmd /c rmdir "$($_.FullName)" | Out-Null }

$distDir = Get-ChildItem $stageDir -Directory -Filter 'cpython-3.11.*-windows-x86_64-none' -ErrorAction SilentlyContinue |
  Select-Object -First 1
if (-not $distDir) { throw "未找到 Python 发行版目录：$stageDir" }

Remove-Item $runtimeDir -Recurse -Force -ErrorAction SilentlyContinue
Move-Item $distDir.FullName $runtimeDir
Remove-Item $stageDir -Recurse -Force -ErrorAction SilentlyContinue

$pythonExe = Join-Path $runtimeDir 'python.exe'
if (-not (Test-Path $pythonExe)) { throw "运行时 python.exe 未找到：$runtimeDir" }

# 2) 安装运行时依赖（不装 torch / sentence-transformers）。
#    uv 管理的独立 CPython 自带 EXTERNALLY-MANAGED 标记，需 --break-system-packages
#    才允许直接写入其 site-packages（这正是目录式运行时的预期行为）。
uv pip install --python $pythonExe --break-system-packages -r $req --index-url $indexUrl

# 3) 验证：核心包可导入
& $pythonExe -c "import fastapi, uvicorn, sqlalchemy, chromadb; print('runtime ok')"

Write-Host "Runtime built at $runtimeDir using $pythonExe"