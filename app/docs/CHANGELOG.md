# CHANGELOG

## 2026-04-25

### Added

- **Тесты RAG (веб):** форма полей `RagRuntimeProfile` (подсказки в `title`), общий блок **«Источники для теста»** (все разделы / выбранные разделы / выбор документов с `document_ids_by_collection`); импорт/экспорт/сохранение профилей по-прежнему как JSON в `localStorage`. Scope тестов независим от области RAG на вкладке «Чат» (`localStorage`: `knowledge_test_scope`).
- **Тесты RAG (A/B):** веб-вкладка «Тесты», API префикс `/v1/rag-test/`: `run`, `compare`, CRUD `profiles`, `main-chat-profile`, `apply-to-chat` (только admin); сохранение прогонов в SQLite (`rag_test_runs`, `rag_test_run_pairs`, `rag_runtime_settings` и др.). `Polza` chat completions: `chat_completion_with_result` возвращает `model` / `provider` / `usage` для диагностики. Основной чат читает safe runtime-overrides из `rag_runtime_settings` (retrieval top-k, temperature, system prompt, distance threshold и т.д.).
- Чат (веб-админка + API): область RAG — **все разделы** (по умолчанию), **один** или **несколько** разделов; retrieval объединяет top‑k по выбранным Chroma-коллекциям. Служебный раздел `__knowledge_rag_all__` в БД для тредов «по всем»; `GET /v1/chat/threads?rag=...` с JSON `{"all":true}` или `{"ids":["..."]}`; `POST /v1/chat/threads` — поле `rag` (альтернатива `collection_id`); у ответа треда — опциональное `rag`.

### Changed

- Веб-админка (чат): цитаты под сообщением ассистента — карточки с текстом и `chunk_id`, не сырой JSON.

### Fixed

- API: при сбое SSL/тайм-ауте при **эмбеддинге Chroma** (загрузка ONNX с S3) чат и `/v1/rag-test/*` отдают **502** с поясняющим `detail` (`app/chroma_user_errors.py`); см. `troubleshooting.md`.
- Веб-админка: **CORS** (по умолчанию `APP_CORS_ORIGINS=*`) — устраняет `TypeError: Failed to fetch` при запросах с другого origin; опционально **APP_PUBLIC_BASE_URL** + `apiPath()`; корень `/` отдаёт `index.html` с подстановкой `__API_BASE__` (`HTMLResponse`).
- Polza/LLM: сетевые сбои до HTTP-ответа (в т.ч. **DNS Errno -3**) маппятся в `LlmUpstreamError` в `app/llm.py`; API чата отдаёт **502** (сеть/DNS) или **504** (таймаут) с читаемым `detail` вместо обобщённого 500.
- `POLZA_BASE_URL`: валидация — только абсолютный URL с `http://` или `https://`.
- `docker-compose.yml`: `dns` 8.8.8.8 / 8.8.4.4 для снижения сбоев резолва в Docker.

## 2026-04-28

### Added

- SQLite: таблицы `chat_threads`, `chat_messages` — персистентная история нескольких чатов на раздел (RAG `collection_id`); при удалении раздела потоки удаляются каскадом (`PRAGMA foreign_keys = ON` в `app/db_sqlite.py`).
- API: `GET/POST /v1/chat/threads`, `GET/PATCH/DELETE /v1/chat/threads/{id}`, `GET /v1/chat/threads/{id}/messages`, `POST /v1/chat/threads/{id}/messages` — тот же ответ `ChatOut`, что у `POST /v1/collections/{id}/chat`, плюс сохранение пары user/assistant в БД.
- Веб-админка: редизайн в духе ChatGPT / дизайн-системы Carbon Logic (референс: `app/docs/design/`); верхние табы «Документы» / «Чат», настройки по иконке шестерёнки; на экране чата слева список чатов, история сообщений, нижний composer (`#chat-thread-list`, `#message-composer`).

### Changed

- `GET /v1/health` и OpenAPI: версия **0.4.0**; `pyproject.toml`: `version = 0.4.0`.
- Веб-админка: drag-and-drop зона загрузки на «Документы»; боковая панель переключается по разделу (чаты только на вкладке «Чат»).

## 2026-04-27

### Added

- Режим отладки: заголовок `X-Debug: 1` (чекбокс «Debug» в Настройках веб-админки) — `POST /v1/.../chat` пишет на сервер шаги RAG/LLM; при 500 в теле ответа (если `APP_ALLOW_CLIENT_DEBUG` не отключён) — `detail` с `error`, `type`, `trace`. Логи `app`/`app.chat_service` в консоли; `APP_ALLOW_CLIENT_DEBUG` в `app/config.py`, `.env.example`. Audit при сбое логируется, ответ чата не теряется.
- Локальный кэш дистрибутивов: каталог `local-dist/` (в `.gitignore`) — `scripts/refresh-local-dist.ps1` скачивает в `local-dist/wheels` актуальные pip/setuptools/wheel и зависимости из `pyproject.toml` (перезапись при обновлении); `-IncludeDockerBase` сохраняет tar базового образа в `local-dist/docker` для `docker load` без Docker Hub. `scripts/refresh-wheels-in-linux-container.ps1` — wheels для **linux**-образа (актуально с Windows + `Dockerfile.wheels`). `scripts/docker-load-base-image-from-cache.ps1` — загрузка сохранённого tar. `scripts/pip-install-editable.ps1` — флаги `-UseLocalDist` и `-TryOnlineFirst`. `Dockerfile.wheels` + `docker-compose.wheels.yml` — сборка образа без PyPI, только из `local-dist/wheels`.
- `scripts/docker-ensure-base-image.ps1` — перед сборкой: локальный `FROM` или `docker load` из tar (обход `context deadline exceeded` к Docker Hub). `scripts/compose-up.ps1` — обёртка над `docker compose up --build` после `docker-ensure-base-image`.
- `GET /v1/health`: поле `auth_configured` (true, если задан любой из `APP_API_KEY` / `APP_ADMIN_KEY` / `APP_MEMBER_KEY`) — публичный сигнал для веб-админки; без ключей (dev) — `false`.
- Веб-админка: левое боковое меню (Документы / Чат / Настройки) с кнопкой сворачивания; по умолчанию открывается экран «Чат»; выбор раздела для чата — выпадающий список; поле `X-API-Key` и работа с localStorage — только при `auth_configured` (в dev без ключей — подсказка без поля; Health в «Настройки»).
- Персист: последний выбранный раздел хранится в `localStorage` (`knowledge_selected_cid`).
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

- Версия API-пакета / health: `0.3.0` (с 2026-04-28 — `0.4.0`, см. верх `CHANGELOG`).
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
