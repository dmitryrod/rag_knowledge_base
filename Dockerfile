# Knowledge API: тот же entrypoint, что и локально — `knowledge-api` (см. pyproject [project.scripts])
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["knowledge-api"]
