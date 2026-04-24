# Загружает базовый образ Python из local-dist\docker\*.tar (после refresh-local-dist.ps1 -IncludeDockerBase),
# чтобы docker compose build не ходил в Docker Hub.
param(
    [string]$TarPath = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $TarPath) {
    $TarPath = Join-Path $Root "local-dist" "docker" "python-3.12-slim-bookworm.tar"
}
if (-not (Test-Path $TarPath)) {
    Write-Error "TAR not found: $TarPath — run: .\scripts\refresh-local-dist.ps1 -IncludeDockerBase"
}
Write-Host "docker load -i $TarPath" -ForegroundColor Green
& docker load -i $TarPath
exit $LASTEXITCODE
