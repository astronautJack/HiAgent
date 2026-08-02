[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
    npm test
    Push-Location tools
    try {
        uv run --group dev pytest
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
