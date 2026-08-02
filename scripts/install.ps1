[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "未找到 git。公司环境应先完成 Git for Windows 配置。"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "未找到 uv。请先运行公司提供的 uv_install.psl，再重新执行本脚本。"
}

$UvBin = (uv tool dir --bin).Trim()
if ($env:Path -notlike "*$UvBin*") {
    $env:Path = "$UvBin;$env:Path"
}

Write-Host "[1/5] 安装或更新 code-review-graph"
uv tool install --force "code-review-graph>=2.3.7,<3.0"

Write-Host "[2/5] 安装 HiAgent CLI"
uv tool install --force (Join-Path $ProjectRoot "tools")

Write-Host "[3/5] 验证命令"
code-review-graph --version
logscope-triage --help | Select-Object -First 2
hiagent-crg --help | Select-Object -First 2
hiagent-run --help | Select-Object -First 2

Write-Host "[4/5] 检查 CodeAgent 配置"
$Settings = Join-Path $ProjectRoot ".cac\settings.json"
if (-not (Test-Path $Settings)) {
    throw "缺少 .cac\settings.json，请确认 clone 的是 codeagent 发行分支。"
}

Write-Host "[5/5] 检查 Wiki 分类配置"
$WikiTargets = Join-Path $ProjectRoot ".cac\wiki-targets.json"
if (-not (Test-Path $WikiTargets)) {
    throw "缺少 .cac\wiki-targets.json"
}
$WikiConfigText = Get-Content -Raw -Path $WikiTargets
$WikiConfigured = -not $WikiConfigText.Contains("REPLACE_WITH_")

Write-Host ""
Write-Host "安装完成。下一步："
if (-not $WikiConfigured) {
    Write-Host "  1. 运行 .\scripts\configure-wiki.ps1，填写 base_url 与当前分类的准确名称"
} else {
    Write-Host "  1. Wiki 分类配置已填写"
}
Write-Host "  2. 在项目根目录运行 codeagent"
Write-Host "  3. 运行 wiki-health；ready=true 后使用核心 workflow"
