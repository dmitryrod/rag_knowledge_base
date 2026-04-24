# Установка пакета в editable mode, когда `pip install -e .` падает на этапе
# "Installing build dependencies" (часто 407 к прокси в изолированной сборке).
# Предусловие: из текущего окружения pip уже может качать пакеты с PyPI (прокси с логином, VPN или прямой доступ),
# иначе сначала почини HTTP(S)_PROXY или поставь setuptools/wheel с флешки.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    Write-Error "pyproject.toml not found next to scripts/; repo layout unexpected."
}
Set-Location $Root

python -c "import setuptools" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "setuptools is missing. Install build tools (needs working PyPI access once):" -ForegroundColor Yellow
    Write-Host "  python -m pip install -U pip setuptools wheel" -ForegroundColor Cyan
    exit 1
}

Write-Host "pip install -e . --no-build-isolation" -ForegroundColor Green
& pip install -e . --no-build-isolation
exit $LASTEXITCODE
