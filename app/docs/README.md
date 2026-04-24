# Документация `app/`

## Запуск приложения в Docker
.\scripts\ensure-app-env.ps1
docker compose up --build
или
docker compose up -d
docker compose down

Каноническая сопутствующая документация для кода и конфигурации в `app/`. Один источник правды по контрактам запуска, конфигурации и эволюции приложения.

**Маркетинг (ICP, позиционирование, GTM, messaging):** [`.cursor/marketing-context.md`](../../.cursor/marketing-context.md) — не дублировать длинные блоки здесь.

**Материалы для продаж (one-pager, сравнение с альтернативами, пилот, outbound):** [`.cursor/marketing-sales-kit.md`](../../.cursor/marketing-sales-kit.md).

## Продукт (целевое направление)

Платформа корпоративных знаний в локальном контуре: загрузка документов, индексация (chunking, embeddings, RAG), чат и структурированные ответы с обязательными цитатами, в перспективе — отчёты и презентации (в т.ч. Marp), опционально видео через ASR. Детальный план по стадиям: `ROADMAP.md`.

## Оглавление

| Файл | Назначение |
|------|------------|
| `CHANGELOG.md` | Заметные изменения поведения, конфигурации, зависимостей. |
| `ARCHITECTURE.md` | Текущее состояние репозитория и целевые модули при появлении кода. |
| `ROADMAP.md` | V1 / V2 / Enterprise и техдолг. |
| `CONTRIBUTING.md` | Правила правок и проверок перед merge. |
| `troubleshooting.md` | Симптом → причина → шаги → проверка. |

## Запуск API (MVP)

Из корня репозитория (где лежит `pyproject.toml`):

1. **Локальная разработка без Docker:** установи зависимости в **любой** среде Python, которую выбрал сам (pip в пользовательскую схему, другое изолированное окружение и т.д.): `pip install -e .` с тем же набором, что в `pyproject.toml`. Репозиторий **не** поставляет и не требует каталог `.venv/`. При `407` / `Installing build dependencies` + `setuptools` см. `troubleshooting.md`; при необходимости: `.\scripts\pip-install-editable.ps1` или `pip install -e . --no-build-isolation`.
2. Скопировать `app/.env.example` → `app/.env`, задать при необходимости `APP_DATA_DIR`, `APP_API_KEY`, `POLZA_*`.
3. Запуск: `knowledge-api` (скрипт из пакета) **или** `uvicorn app.main:app --host 0.0.0.0 --port 8000` с `PYTHONPATH` на корень workspace (иначе импорт `app` не найдётся). В браузере по умолчанию открывай **`/`** — статическая **веб-админка** (`app/static/index.html`); Swagger: `/docs`. При старте в лог печатаются URL (порт в Docker чаще 8002). Порт HTTP: `PORT` / `APP_PORT`; в Docker — `APP_EXPOSED_PORT` в логе.

**Docker Compose** (рекомендуется; корень репо, `docker-compose.yml`):

1. `copy app\.env.example app\.env` (один раз; для dev с пустыми ключами достаточно) или `.\scripts\ensure-app-env.ps1`.
2. Порт на хосте по умолчанию **8002** (у контейнера внутри по-прежнему 8000). **8000 на машине** часто занят другим stack в Docker (например `app-1:8000:8000`). Смена порта: скопируй `env.docker.example` → **`.env`** в корне репозитория и задай `KNOWLEDGE_API_PORT` (см. пример), либо `set KNOWLEDGE_API_PORT=8010` перед запуском.
3. Сборка и запуск: `docker compose up --build` или в фоне: `docker compose up -d` (эквивалент: `docker-compose up -d`, если стоит старый CLI).
4. Админка: `http://127.0.0.1:8002/` · health: `http://127.0.0.1:8002/v1/health` (или твой `KNOWLEDGE_API_PORT`).

**Только `docker run`** (без compose): `docker build -t knowledge-api:local .` → `docker run --rm -p 8002:8000 --env-file app/.env -e APP_DATA_DIR=/data -v knowledge-data:/data knowledge-api:local` (том `knowledge-data` для Chroma/SQLite). Без `app/.env` в compose нужен созданный файл из `app/.env.example` (см. п.1).

Публично без ключа: `GET /v1/health`. Если задан любой из `APP_API_KEY` (admin), `APP_ADMIN_KEY`, `APP_MEMBER_KEY` — передавать ключ в заголовке. Создание разделов, ingest, удаление, `GET /v1/audit` — только admin; список разделов/документов, `POST .../chat`, `POST .../chat/export` — admin или member. Вынос LLM: `ALLOW_LLM_EGRESS` и `POLZA_CHAT_MODEL_ALLOWLIST` — см. `app/.env.example`.

## Быстрые ссылки

- Переменные окружения (шаблон): `app/.env.example`
- История изменений: `CHANGELOG.md`
- Типовые сбои: `troubleshooting.md`
