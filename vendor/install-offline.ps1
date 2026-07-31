# 安装 CRG + logscope-triage
# 用法：在 PowerShell 里 cd 到项目根目录，运行：
#   powershell -ExecutionPolicy Bypass -File vendor\install-offline.ps1
# 前提：uv 已在 PATH（内网已装好）

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Wheels = Join-Path $ScriptDir "wheels-win"

Write-Host "=== 1. 验证 uv ===" -ForegroundColor Cyan
& uv --version
if ($LASTEXITCODE -ne 0) { Write-Error "uv 不在 PATH"; exit 1 }

Write-Host "=== 2. 装 CRG (code-review-graph) ===" -ForegroundColor Cyan
# 先试直装（PyPI 通了就直接装）
& uv tool install code-review-graph 2>&1 | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Host "直装失败，走离线 wheel..." -ForegroundColor Yellow
    & uv tool install code-review-graph --no-index --find-links $Wheels 2>&1 | ForEach-Object { Write-Host $_ }
}

Write-Host "=== 3. 装 logscope-triage ===" -ForegroundColor Cyan
Push-Location (Join-Path $ProjectRoot "tools")
& uv tool install . 2>&1 | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Host "直装失败，走离线 wheel..." -ForegroundColor Yellow
    & uv tool install . --no-index --find-links $Wheels 2>&1 | ForEach-Object { Write-Host $_ }
}
Pop-Location

Write-Host "=== 4. 验证 ===" -ForegroundColor Cyan
& code-review-graph --version
& logscope-triage --help | Select-Object -First 1
Write-Host "=== 全部就绪 ===" -ForegroundColor Green
