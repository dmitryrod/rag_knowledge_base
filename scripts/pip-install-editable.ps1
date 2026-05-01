# Установка пакета в editable mode, когда `pip install -e .` падает на этапе
# "Installing build dependencies" (часто 407 к прокси в изолированной сборке).
#
# -UseLocalDist  — только из local-dist/wheels (см. scripts\refresh-local-dist.ps1)
# -TryOnlineFirst — сначала обычный pip, при ошибке — из local-dist/wheels
param(
    [switch]$UseLocalDist,
    [switch]$TryOnlineFirst
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    Write-Error "pyproject.toml not found next to scripts/; repo layout unexpected."
}
Set-Location $Root

$Wheels = Join-Path (Join-Path $Root "local-dist") "wheels"
function Install-FromLocalWheels {
    if (-not (Test-Path $Wheels)) {
        Write-Error "No directory $Wheels — run: .\scripts\refresh-local-dist.ps1"
    }
    $hasAny = Get-ChildItem -File $Wheels -ErrorAction SilentlyContinue
    if (-not $hasAny) {
        Write-Error "Wheels directory is empty — run: .\scripts\refresh-local-dist.ps1"
    }
    Write-Host "pip install (offline) from $Wheels" -ForegroundColor Green
    & pip install --no-index --find-links $Wheels -U pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { return $LASTEXITCODE }
    & pip install -e . --no-build-isolation --no-index --find-links $Wheels
    return $LASTEXITCODE
}

if ($UseLocalDist) {
    $code = Install-FromLocalWheels
    exit $code
}

if ($TryOnlineFirst) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Error "python not in PATH"
    }
    & pip install -e . --no-build-isolation
    if ($LASTEXITCODE -eq 0) { exit 0 }
    Write-Host "Online install failed. Retrying with local-dist/wheels..." -ForegroundColor Yellow
    if (-not (Test-Path $Wheels)) {
        Write-Error "No local cache at $Wheels — run with network: .\scripts\refresh-local-dist.ps1"
    }
    $code = Install-FromLocalWheels
    exit $code
}

python -c "import setuptools" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "setuptools is missing. Install build tools (needs working PyPI access once):" -ForegroundColor Yellow
    Write-Host "  python -m pip install -U pip setuptools wheel" -ForegroundColor Cyan
    exit 1
}

Write-Host "pip install -e . --no-build-isolation" -ForegroundColor Green
& pip install -e . --no-build-isolation
exit $LASTEXITCODE
