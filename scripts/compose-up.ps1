# Сначала гарантирует базовый образ (docker-ensure-base-image), затем docker compose up --build.
# Остаток аргументов уходит в compose, например: .\scripts\compose-up.ps1 -d
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
& (Join-Path $Root "scripts" "docker-ensure-base-image.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location $Root
$tail = $args
if ($tail -and $tail.Count -gt 0) {
    & docker compose up --build @tail
} else {
    & docker compose up --build
}
exit $LASTEXITCODE
