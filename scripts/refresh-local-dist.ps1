# Скачивает в local-dist/ артефакты для работы с сетью/без (обновляй при удачном доступе к PyPI / Docker Hub):
#   local-dist/wheels/ — pip, setuptools, wheel, зависимости и пакет из pyproject (перезапись = актуальные версии)
#   local-dist/docker/  — опционально: tar базового образа (см. -IncludeDockerBase) для docker load без pull
# Использование: .\scripts\refresh-local-dist.ps1 [-IncludeDockerBase] [-BaseImage "python:3.12-slim-bookworm"]
param(
    [switch]$IncludeDockerBase,
    [string]$BaseImage = "python:3.12-slim-bookworm"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$WheelsDir = Join-Path $Root "local-dist" "wheels"
$DockerDir = Join-Path $Root "local-dist" "docker"
New-Item -ItemType Directory -Force -Path $WheelsDir, $DockerDir | Out-Null

if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    Write-Error "pyproject.toml not found in repo root."
}

Write-Host "Downloading wheels into $WheelsDir (exists-action: replace with newest)..." -ForegroundColor Green
& python -m pip download --dest $WheelsDir --exists-action w pip "setuptools>=61" wheel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& python -m pip download --dest $WheelsDir --exists-action w .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$fc = (Get-ChildItem -File $WheelsDir -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "Wheels done ($fc file(s))." -ForegroundColor Cyan

if ($IncludeDockerBase) {
    $safeName = $BaseImage -replace "[:/]", "-"
    $outTar = Join-Path $DockerDir ($safeName + ".tar")
    Write-Host "Pulling and saving $BaseImage -> $outTar" -ForegroundColor Green
    & docker pull $BaseImage
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & docker save $BaseImage -o $outTar
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Saved. Пока сеть плохая: docker load -i `"$outTar`" затем сборка с docker-compose.wheels.yml" -ForegroundColor Cyan
}

Write-Host "Установка из кэша: .\\scripts\\pip-install-editable.ps1 -UseLocalDist" -ForegroundColor Cyan
Write-Host "Docker без PyPI внутри build: sm. docker-compose.wheels.yml (нужен local-dist/wheels + при необходимости docker load)" -ForegroundColor Cyan
exit 0
