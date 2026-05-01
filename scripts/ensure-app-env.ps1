# Перед `docker compose up`: копирует app/.env.example -> app/.env, если .env нет
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$wheelsDir = Join-Path $Root "local-dist\wheels"
New-Item -ItemType Directory -Force -Path $wheelsDir | Out-Null
$envExample = Join-Path $Root "app\.env.example"
$envTarget = Join-Path $Root "app\.env"
if (Test-Path $envTarget) {
    Write-Host "app/.env already exists" -ForegroundColor Cyan
    exit 0
}
if (-not (Test-Path $envExample)) {
    Write-Error "Missing app/.env.example"
}
Copy-Item $envExample $envTarget
Write-Host "Created app/.env from app/.env.example" -ForegroundColor Green
