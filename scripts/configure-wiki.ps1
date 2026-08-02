[CmdletBinding()]
param(
    [string]$BaseUrl
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Value([string]$Value, [string]$Prompt) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        $Value = Read-Host $Prompt
    }
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Prompt 不能为空"
    }
    if ($Value.Contains("REPLACE_WITH_")) {
        throw "$Prompt 不能包含占位符 REPLACE_WITH_"
    }
    return $Value.Trim()
}

function Prompt-CategoryName([string]$CurrentValue, [string]$Prompt) {
    if ($CurrentValue.Contains("REPLACE_WITH_")) {
        $CurrentValue = ""
    }
    if ([string]::IsNullOrWhiteSpace($CurrentValue)) {
        return Require-Value "" $Prompt
    }
    $Entered = Read-Host "$Prompt（当前：$CurrentValue；直接回车保留）"
    if ([string]::IsNullOrWhiteSpace($Entered)) {
        return $CurrentValue.Trim()
    }
    return Require-Value $Entered $Prompt
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $ProjectRoot ".cac\wiki-targets.json"
if (-not (Test-Path $Target)) {
    throw "缺少 $Target"
}

$Config = Get-Content -Raw -Path $Target | ConvertFrom-Json
if ($Config.schema_version -ne "hiagent.wiki-targets.v2") {
    throw "wiki-targets.json schema 不兼容，期望 hiagent.wiki-targets.v2"
}

$BaseUrl = Require-Value $BaseUrl "Wiki base_url（只作为导航起点，禁止直接写入）"
$Config.base_url = $BaseUrl

if (@($Config.categories).Count -eq 0) {
    throw "categories 至少需要一项"
}

foreach ($Category in @($Config.categories)) {
    foreach ($RequiredProperty in @("key", "name", "description")) {
        if ($null -eq $Category.PSObject.Properties[$RequiredProperty]) {
            throw "每个 category 都必须包含 key、name、description；当前缺少 $RequiredProperty"
        }
    }
    $Prompt = "分类 '$($Category.key)' 的内网准确名称（用途：$($Category.description)）"
    $CurrentName = [string]$Category.name
    $Category.name = Prompt-CategoryName $CurrentName $Prompt
}

$Keys = @($Config.categories | ForEach-Object { ([string]$_.key).Trim().ToLowerInvariant() })
$Names = @($Config.categories | ForEach-Object { ([string]$_.name).Trim().ToLowerInvariant() })
if (($Keys | Select-Object -Unique).Count -ne $Keys.Count) {
    throw "categories.key 不能重复"
}
if (($Names | Select-Object -Unique).Count -ne $Names.Count) {
    throw "分类准确名称不能重复"
}

$RouteProperties = @($Config.routes.PSObject.Properties)
if (-not ($RouteProperties.Name -contains "default")) {
    throw "routes 必须包含 default"
}
foreach ($Route in $RouteProperties) {
    if ($Keys -notcontains ([string]$Route.Value).ToLowerInvariant()) {
        throw "route '$($Route.Name)' 指向不存在的 category key '$($Route.Value)'"
    }
}

$Config | ConvertTo-Json -Depth 8 | Set-Content -Path $Target -Encoding UTF8

Write-Host "已写入 $Target"
Write-Host "脚本不会拼接子目录 URL；wiki-gateway 会通过 wiki-mcp 在 base_url 下按准确名称导航。"
Write-Host "请启动/重启 codeagent，然后运行 wiki-health。"
