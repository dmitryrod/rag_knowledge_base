# Кладёт в local-dist/wheels колёса **внутри** python:3.12-slim (linux manylinux) через `docker run -v`.
# На Docker Desktop для Windows это надёжный способ: при `docker build` bind-mount записи
# в host D:\ часто не сохран (сборка в VM), а `docker run` монтирует каталог в рантайме — файлы видны в Explorer.
#
# Нужны Docker и сеть (или docker load базы). Дальше: docker compose build --build-arg WHEEL_MODE=offline
param([string]$Image = "python:3.12-slim")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$wMount = Join-Path (Join-Path $Root "local-dist") "wheels"
New-Item -ItemType Directory -Force -Path $wMount | Out-Null

Write-Host "pip wheel -> local-dist\wheels (image: $Image)" -ForegroundColor Green
# Без --no-build-isolation pip снова тянет setuptools в изолированном subprocess с PyPI (SSL/timeout).
# Сначала wheelhouse, затем pip install из него в основное окружение, затем pip wheel без изоляции.
# Одна строка для bash -c: многострочный here-string ломает проброс аргументов из PowerShell в docker.
# pip 26+: wheel проекта из `pip wheel .` кладётся в /tmp/pip-ephem-wheel-cache и затем каталог удаляется — find после команды опоздывает.
# Явный `python -m build --wheel --outdir` кладёт rag_knowledge_base-*.whl сразу в wheelhouse (build уже тянется как зависимость chromadb в шаге pip wheel).
$bashCmd = 'set -e; export PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10; W=/work/local-dist/wheels; pip install -U pip; pip download "setuptools>=61" wheel -d "$W"; pip install --no-index --find-links="$W" "setuptools>=61" wheel; pip wheel --no-build-isolation --no-cache-dir . -w "$W"; pip install --no-index --find-links="$W" build; python -m build --wheel --no-isolation --outdir "$W"'
& docker run --rm `
  -e PIP_DEFAULT_TIMEOUT=120 `
  -e PIP_RETRIES=10 `
  -v "$($Root):/work" `
  -w /work `
  $Image `
  bash -lc $bashCmd
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. Next: docker compose build --build-arg WHEEL_MODE=offline" -ForegroundColor Cyan
exit 0
