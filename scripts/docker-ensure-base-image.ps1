# Проверяет локальный образ (как в Dockerfile FROM). Если нет — docker load из tar в local-dist\docker\.
# Без образа и без tar сборка идёт в Docker Hub (часто: context deadline exceeded).
# Запускай ПЕРЕД docker compose up --build, если Hub недоступен.
param(
    [string]$Image = "python:3.12-slim-bookworm",
    [string]$TarPath = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $TarPath) {
    $file = ($Image -replace "[:/]", "-") + ".tar"
    $TarPath = Join-Path $Root "local-dist" "docker" $file
}

$null = & docker image inspect $Image 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Base image $Image already local — no Hub needed for FROM." -ForegroundColor Green
    exit 0
}

if (Test-Path $TarPath) {
    Write-Host "docker load -i $TarPath" -ForegroundColor Cyan
    & docker load -i $TarPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "OK. Next: docker compose up --build" -ForegroundColor Green
    exit 0
}

Write-Host "ERROR: No local image '$Image' and no TAR:" -ForegroundColor Red
Write-Host "  $TarPath" -ForegroundColor Red
Write-Host ""
Write-Host "Сделай ОДНО:" -ForegroundColor Yellow
Write-Host "  1) При доступе к Hub:  docker pull $Image" -ForegroundColor Cyan
Write-Host "  2) С другой машины:   .\scripts\refresh-local-dist.ps1 -IncludeDockerBase, скопируй local-dist\docker\*.tar сюда" -ForegroundColor Cyan
Write-Host "  3) VPN / DNS / зеркало — см. app\docs\troubleshooting.md" -ForegroundColor Cyan
exit 1
