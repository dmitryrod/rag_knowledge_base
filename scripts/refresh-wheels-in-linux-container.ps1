# Кладёт в local-dist/wheels пакеты, скачанные **внутри** образа python:3.12-slim-bookworm (linux),
# чтобы `Dockerfile.wheels` на Windows-хосте не ломался из-за win_amd64 vs manylinux.
# Нужен Docker и доступ к сети (pull образа + PyPI) или заранее: docker load из refresh-local-dist.ps1 -IncludeDockerBase
param([string]$Image = "python:3.12-slim-bookworm")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Wheels = "/work/local-dist/wheels"
# docker -v: Windows путь
$wMount = (Join-Path $Root "local-dist" "wheels")
New-Item -ItemType Directory -Force -Path $wMount | Out-Null

Write-Host "Downloading wheels inside $Image (linux) -> local-dist\wheels" -ForegroundColor Green
# bash -c: обновляем pip в контейнере, затем качаем build-tools и зависимости проекта
$inner = "pip install -U pip && pip download --dest $Wheels --exists-action w pip 'setuptools>=61' wheel && pip download --dest $Wheels --exists-action w ."
& docker run --rm -v "$($Root):/work" -w /work $Image bash -c $inner
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. Use: docker compose -f docker-compose.yml -f docker-compose.wheels.yml build" -ForegroundColor Cyan
exit 0
