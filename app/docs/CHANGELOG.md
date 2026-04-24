# CHANGELOG

## 2026-04-27

### Added

- Веб-админка: при отправке сообщения в чат показывается индикатор «LLM в работе…» (спиннер) справа от кнопки «Отправить», кнопка блокируется до ответа.

### Changed

- Веб-админка: в UI термин «Коллекции» заменён на «Разделы» (заголовок, плейсхолдеры, подтверждение удаления).
- Polza: температура из настроек `POLZA_TEMPERATURE`, по умолчанию **0** (было захардкожено 0.2 в `llm.py`).

## 2026-04-26

### Fixed

- `chat_service.run_chat`: при удалённой LLM и ответе «НЕ НАЙДЕНО» с пустыми `citations` теперь подставляются цитаты из retrieval (как в режиме без egress). System-prompt: не злоупотреблять «НЕ НАЙДЕНО», если фрагменты релевантны.

### Added

- `app/tests/test_chat_service.py` — мок Polza и проверка fallback citations.

## 2026-04-25

### Added

- `GET /` — отдача веб-админки (`app/static/index.html`): разделы, загрузка файлов, чат, ссылка на `/docs`. Ключ API опционально в localStorage; операции admin требуют admin-ключ на сервере.
- `app/tests/test_api.py::test_root_serves_admin_ui`

### Changed

- Убран редирект `/` → `/docs` (раньше поэтому в браузере открывался только Swagger).

## 2026-04-24

### Changed

- Репозиторий не сопровождает и не требует `.venv/`: в `.gitignore` явно `.venv/`, `venv/`. Каталог `.venv` у разработчика — не артефакт репо; путь «как в проде» — Docker. `GET /` → редирект на `/docs`. При старте — печать URL; в Docker `APP_EXPOSED_PORT` / `KNOWLEDGE_API_PORT` (по умолчанию 8002). Порты: `PORT` / `APP_PORT`.
- `.vscode/settings.json`: `python.terminal.activateEnvironment: false` — не авто-активировать venv в встроенном терминале.

### Docs

- `README.md`, `troubleshooting.md`, `CONTRIBUTING.md`: без обязательного venv; `ERR_CONNECTION_REFUSED` / порты.

## 2026-04-23

### Added

- `docker-compose.yml` — сервис `knowledge-api`, порт хоста по умолчанию **8002** (избегаем конфликта с типичным `8000:8000` у другого stack), том `knowledge_data`, `APP_DATA_DIR=/data`, `env_file: app/.env`.
- `env.docker.example` — шаблон для корневого `.env` (`KNOWLEDGE_API_PORT` для compose).
- `scripts/ensure-app-env.ps1` — создать `app/.env` из `app/.env.example`, если отсутствует.
- `scripts/pip-install-editable.ps1` — editable install с `--no-build-isolation` после ручной установки `setuptools`/`wheel` (см. `troubleshooting` при 407 / «Installing build dependencies»).

### Docs

- `troubleshooting.md`, `README.md`: прокси 407, `getaddrinfo` на хосте, Docker/compose и порты.

## 2026-04-15 (V1 hardening)

### Added

- RBAC: опциональные `APP_ADMIN_KEY` / `APP_MEMBER_KEY`; legacy `APP_API_KEY` = admin. Member: список разделов/документов, чат, `POST .../chat/export`; admin: создание/удаление разделов и документов, ingest, `GET /v1/audit`.
- Политика LLM: `ALLOW_LLM_EGRESS` (по умолчанию `false` — без вызова Polza); опциональный `POLZA_CHAT_MODEL_ALLOWLIST` при включённом egress.
- `POST /v1/collections/{id}/chat/export?format=markdown|plain` — экспорт ответа с цитатами.
- RAG: принудительные citations из топ-chunk при ответе модели без цитат (кроме явного «не найдено»); demo-режим даёт цитаты к извлечённым фрагментам.

### Changed

- Версия API-пакета / health: `0.3.0`.
- `pyproject.toml`: `[build-system]` и явный поиск пакета `app` для `pip install -e .`.

### Docs

- `troubleshooting.md`: таймаут PyPI / `setuptools` при `pip install -e .`; прокси `407` и `Cannot import setuptools.build_meta`.

## 2026-04-15

### Added (MVP backend)

- FastAPI-приложение в `app/`: разделы и документы (SQLite-метаданные + Chroma), ingest с chunking, чат RAG с JSON-цитатами и опциональным Polza LLM (`app/chat_service.py`, `app/llm.py`). Точка входа `app.main`, скрипт `knowledge-api`. Тесты: `with TestClient(...)` для запуска lifespan (`init_stores`).
- Обновлён `app/.env.example` под Knowledge API (`APP_DATA_DIR`, `APP_API_KEY`, `POLZA_*`).
- В `troubleshooting.md`: кейс `Stores not initialized` в тестах с `TestClient`.

### Docs

- Добавлен `.cursor/marketing-sales-kit.md`: one-pager для ИБ, сравнительная таблица, протокол пилота, два варианта cold outbound, гайд интервью; ссылки из `marketing-context.md` и `app/docs/README.md`. Обновление: исполняемый чеклист «что дальше» на 2 недели (§7–8).
- Обновлён `.cursor/marketing-context.md`: секция follow-up маркетингового исследования (2026-04-15), ссылки на sales-kit.
- Добавлен `.cursor/marketing-context.md` (канон ICP, позиционирование, GTM-скелет, возражения); в `README.md` добавлена ссылка без копипасты.
- Обновлены `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`: целевое направление продукта (локальный knowledge/RAG), дорожная карта V1 → V2 → Enterprise; после появления кода MVP — раздел «Запуск API» в `README.md` и таблица модулей в `ARCHITECTURE.md`.
- Ранее: базовый комплект `app/docs/`, `pyproject.toml`, начальный smoke-test в `app/tests/`.
