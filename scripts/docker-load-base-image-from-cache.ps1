# Загружает базовый образ Python из local-dist\docker\*.tar (после refresh-local-dist.ps1 -IncludeDockerBase),
# чтобы docker compose build не ходил в Docker Hub.
param(
    [string]$Image = "python:3.12-slim",
    [string]$TarPath = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $TarPath) {
    $file = ($Image -replace "[:/]", "-") + ".tar"
    $TarPath = Join-Path (Join-Path (Join-Path $Root "local-dist") "docker") $file
}
if (-not (Test-Path $TarPath)) {
    Write-Error "TAR not found: $TarPath — run: .\scripts\refresh-local-dist.ps1 -IncludeDockerBase [-BaseImage `"$Image`"]"
}
Write-Host "docker load -i $TarPath" -ForegroundColor Green
& docker load -i $TarPath
exit $LASTEXITCODE
