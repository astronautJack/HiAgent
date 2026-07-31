# 离线安装 uv + CRG + logscope-triage（Windows，无外网）
# 用法：在 PowerShell 里 cd 到项目根目录，运行：
#   powershell -ExecutionPolicy Bypass -File vendor\install-offline.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Wheels = Join-Path $ScriptDir "wheels-win"
$UvExe = Join-Path $ScriptDir "uv.exe"

Write-Host "=== 1. 装 uv ===" -ForegroundColor Cyan
$uvDir = Join-Path $env:USERPROFILE ".local\bin"
if (!(Test-Path $uvDir)) { New-Item -ItemType Directory -Path $uvDir -Force | Out-Null }
Copy-Item $UvExe (Join-Path $uvDir "uv.exe") -Force
$env:PATH = "$uvDir;$env:PATH"
Write-Host "uv 已装到 $uvDir\uv.exe"

Write-Host "=== 2. 装 CRG (code-review-graph) ===" -ForegroundColor Cyan
$env:UV_TOOL_DIR = Join-Path $env:USERPROFILE ".local\share\uv\tools"
& uv tool install code-review-graph --no-index --find-links $Wheels 2>&1 | ForEach-Object { Write-Host $_ }

Write-Host "=== 3. 装 logscope-triage ===" -ForegroundColor Cyan
Push-Location (Join-Path $ProjectRoot "tools")
& uv tool install . --no-index --find-links $Wheels 2>&1 | ForEach-Object { Write-Host $_ }
Pop-Location

Write-Host "=== 4. 验证 ===" -ForegroundColor Cyan
& uv --version
$global:PATH = "$uvDir;$global:PATH"
& code-review-graph --version
& logscope-triage --help | Select-Object -First 1
Write-Host "=== 全部就绪 ===" -ForegroundColor Green
Write-Host ""
Write-Host "注意：确保 $uvDir 在 PATH（加到系统环境变量）"
