# Не указывать `# syntax=docker/dockerfile:1`: иначе BuildKit тянет frontend с Docker Hub (при резке сети/registry сборка падает).
# Knowledge API: entrypoint `knowledge-api` (см. pyproject [project.scripts]).
#
# Сборка offline без compose (нужен контекст wheelhouse):
#   docker buildx build -t knowledge-api:local --build-arg WHEEL_MODE=offline \
#     --build-context wheelhouse=./local-dist/wheels -f Dockerfile .
#
# WHEEL_MODE:
#   online  — ставит зависимости из PyPI (без bind на колёса). На Docker Desktop для Windows
#             запись в bind при docker build часто НЕ попадает на диск D:\ — см. README и
#             scripts/refresh-wheels-in-linux-container.ps1 для заполнения local-dist/wheels.
#   offline — только local-dist/wheels (bind, ro). Колёса заранее: тот же скрипт или online-сборка на Linux.
#
# BuildKit нужен для RUN --mount (режим offline).
FROM python:3.12-slim

ARG WHEEL_MODE=online

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_RETRIES=10

COPY pyproject.toml ./
COPY app ./app

# Online: обычная установка по сети (надёжно на Windows).
RUN set -eu; \
    if [ "${WHEEL_MODE}" = "online" ]; then \
      pip install --upgrade pip && \
      pip install --no-cache-dir -e .; \
    fi

# Offline: колёса из named context `wheelhouse` (compose: additional_contexts).
# Не type=bind,source=local-dist/wheels — при docker build на Docker Desktop для Windows /wheels часто пустой.
RUN --mount=from=wheelhouse,target=/wheels,ro \
    set -eu; \
    if [ "${WHEEL_MODE}" != "offline" ]; then exit 0; fi; \
    pip install --no-index --find-links=/wheels --upgrade pip setuptools wheel && \
    pip install --no-index --find-links=/wheels --no-cache-dir -e .

EXPOSE 8000
CMD ["knowledge-api"]
