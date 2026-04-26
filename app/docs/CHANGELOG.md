# CHANGELOG

## 2026-04-26 (RAG scope / чат)

### Changed

- **Веб-админка, «Настройки»:** переключатель отладки вместо чекбокса; убрана карточка-переход «Тесты качества RAG» (вкладка **«Тесты»** и A/B по-прежнему в шапке). Добавлен выбор цветовой схемы (тёмная / светлая / синяя / розовая / серая): `data-theme` на `<html>`, токены в CSS, сохранение в `localStorage` (`knowledge_theme`) (`app/static/index.html`).
- **Веб-админка, тема «Серая»:** палитра поверхностей и акцентов ещё раз осветнена; границы и вторичный текст чуть мягче для менее «угольного» вида (`app/static/index.html`).
- **Веб-админка, тема «Розовая»:** фоновые токены светлее, акцент и контейнеры — пастельный тусклый розовый (согласованы `--primary*`, границы, focus) (`app/static/index.html`).
- **Веб-админка, вкладка «Чат»:** после отправки сообщение пользователя сразу попадает в историю; до ответа LLM показывается плейсхолдер ассистента («Думаю…»); по успеху или ошибке лента обновляется с сервера (`app/static/index.html`).
- **Веб-админка, вкладка «Тесты»:** после «Сравнить A/B» результат показывается **таблицей** (параметр, колонки A/B, вывод: дельты для чисел, «только в A/B», краткий текст ответа без простыни JSON); полный ответ `POST /v1/rag-test/compare` по-прежнему в свёрнутом блоке «Показать raw JSON». Восстановление из избранного подхватывает `run_meta.last_compare` или парсит сохранённую строку JSON (`app/static/index.html`).
- **Веб-админка, вкладка «Тесты»:** таблица результата A/B **без** `max-height` и без внутренней вертикальной прокрутки — высота по контенту, страница удлиняется; при узком экране у обёртки остаётся только горизонтальный скролл (`app/static/index.html`).
- **Веб-админка, вкладка «Тесты»:** в таблице A/B поле `answer` выводится **полностью** (без обрезки `…`); для колонок A/B включены переносы строк и разбиение длинных слов (`app/static/index.html`).
- **Веб-админка, вкладка «Тесты»:** `pair_id` после «Сравнить A/B» показывается **один раз** справа над блоком «Ответ A / Ответ B», а не внутри карточек; при прогоне только A/B бейдж сбрасывается; при загрузке избранного — из `run_meta.last_compare` или из сохранённого JSON сравнения (`app/static/index.html`).
- **Метрики RAG-тестов:** `answer_hash` и `citation_set_hash` считаются через строгий `encode("utf-8")` без `errors="replace"` — `app/rag_test_service.py`.

### Fixed

- **Веб-админка, вкладка «Тесты»:** уменьшен верхний `padding` у `#view-tests .view-inner--tests` (заголовок «A/B-тесты» ближе к `.topbar`); остальные отступы и карточки не трогались (`app/static/index.html`).

- **Веб-админка, вкладка «Чат»:** уменьшен верхний зазор до блока «Выбор документов» — у `#headStatus` убраны дефолтный margin у `<p>` и лишний `min-height` в пустом состоянии (`.head-status:not(:empty)` оставляет полосу при показе статуса) (`app/static/index.html`).

- **Веб-админка, лейаут:** высота заголовка левой колонки (`.sidebar-head`) выровнена с верхней панелью вкладок (`.topbar`, `--top-h`), чтобы убрать «ступень» на стыке сайдбара и контента на всех вкладках (`app/static/index.html`).

- **Веб-админка, шапка:** вкладки «Документы / Чат / Тесты» — явное выделение **активной** вкладки без наведения; hover **неактивных** визуально отличается (внутренняя кайма, без «пилюли» как у выбранной); `aria-selected` синхронизируется в `setView` (`app/static/index.html`).

- **Ingest (`.txt` / `.md` / `.csv` / `.html`):** плоский текст сначала декодируется как UTF-8 (включая BOM); при невалидном UTF-8 — **Windows-1251**, без `errors="replace"`, чтобы в чанках Chroma и в ответах RAG (в т.ч. на вкладке «Тесты») не появлялись символы замены U+FFFD (`��`) из‑за исходников в Windows-1251 вместо UTF-8. Уже проиндексированные чанки с битыми символами нужно **перезалить** документ.
- **RAG чат и тесты:** выбранный раздел (и явный список разделов) **раскрывается на все подразделы** в SQLite — поиск в Chroma идёт по объединённому списку коллекций; исправляет «не найдено», когда документ лежит во вложенной папке, а в UI отмечен только родитель (`app/rag_scope.py`, `app/routers/api.py`, `app/rag_test_service.py`).
- **Перенос документов в Chroma:** перед `add` в целевую коллекцию удаляются чанки этого `document_id` в цели — повторное копирование не удваивает векторы (`app/chroma_store.py`).
- **Чат + LLM:** если модель отвечает «не найдено» с пустыми `citations`, но retrieval лексически совпадает с вопросом (например `фанера` / `фанеры`, `сорта`), чат возвращает локальный extractive fallback с цитатами; нерелевантный top-k по-прежнему не маскируется (`app/chat_service.py`).
- **Debug:** при `X-Debug: 1` в теле ответа чата опционально поле `debug` (`collection_ids`, счётчики, превью чанков, distance и **`retrieval_encoding`** — чанки retrieval с U+FFFD в тексте, см. `replacement_char_report` в `app/chat_service.py`).

### Added

- **RAG-тесты / отладка:** при `debug: true` в `POST /v1/rag-test/run` в ответе добавляется `debug.retrieval_encoding` (та же семантика, что у чата) — `app/rag_test_service.py`.
- **Регрессия UTF-8:** сохранение русского текста без U+FFFD по цепочке LLM → SQLite → `GET /v1/chat/threads/.../messages` — `app/tests/test_api.py::test_chat_thread_messages_preserve_utf8_no_replacement_char`; прогон «Тесты» + A/B с моком LLM — `app/tests/test_rag_test_api.py::test_rag_test_run_and_compare_preserve_utf8_no_replacement_char`; unit-тесты отчёта по чанкам — `app/tests/test_chat_service.py` (`replacement_char_report`).
- **API:** `DELETE /v1/rag-test/main-chat-profile` — сброс серверных overrides основного чата (`app/routers/rag_test.py`, `app/db_sqlite.py::delete_rag_runtime_settings`).
- **Веб-админка:** кнопка «Сбросить overrides чата» в настройках; после DnD документа **обновляется** `knowledge_rag_scope` (подмена старого `collection_id` на новый в выбранных разделах) (`app/static/index.html`).

## 2026-04-26

### Changed

- Веб-админка (`app/static/index.html`): подтверждения и ввод имён (переименование чата/раздела/файла, удаление чата, раздела, документа, избранного теста) через **кастомные модальные окна** в стиле дизайн-системы (glass overlay, токены поверхности/primary/error); нативные `window.confirm` / `window.prompt` не используются. Сообщения об ошибках по-прежнему через `showHead` / `errBox`, не через `alert()`.

### Added

- Веб-админка, дерево **Документы**: **мультивыбор** файлов — `Ctrl`/`Cmd`+клик (toggle), `Shift`+клик (диапазон в порядке обхода дерева), `Escape` сбрасывает выбор. Drag **выбранного** элемента переносит **все выбранные** документы **по очереди** через `POST .../move`; **«Корень»** для группы документов по-прежнему запрещён. Строка статуса/спиннер + компактный лог `kbTreeMoveLog` (очередь / в процессе / готово / пропуск / ошибка по имени файла) и итог `Готово: N, пропущено: …, ошибок: …`. Во время очереди повторный drag заблокирован.

### Changed

- Веб-админка, вкладка **«Чат»**: лента сообщений и composer без `max-width: 820px` и центрирования — на всю ширину workspace; блок выбора разделов (`#view-chat .rag-scope-box`) без узкого `max-width`, тянется вместе с toolbar. Заголовок переименован в **«Выбор документов»**; блок списка чекбоксов **сворачивается** по клику на строку заголовка (шеврон **слева** от текста, ▼/поворот), состояние только в сессии.
- Веб-админка, вкладка «Документы»: основная колонка (статистика, «База знаний», карточка раздела) на **полную ширину** workspace между сайдбаром и правым краем окна; сняты общие для `.view-inner` ограничение `max-width: 900px` и центрирование только для этого вида.
- Веб-админка, вкладка «Документы» — дерево слева: более компактные отступы строк и вложенности; **DnD** переносится **за иконку** папки/файла (старые ручки `⋮⋮` убраны); иконка подсвечивается при наведении. У **обрезанного** `ellipsis` текста в `title` подставляется **полное имя** (для файлов — как в данных, с расширением); у полностью видимой подписи `title` не дублирует текст. Подписка на `resize` панели и `ResizeObserver` на контейнере дерева — пересчёт подсказок при смене ширины сайдбара.

### Fixed

- **DnD в дереве:** на SVG внутри иконки папки/файла `pointer-events: none`, чтобы перетаскивание инициализировалось с `draggable`‑обёртки (как у бывшего текстового handle). `dragover` больше не требует только `treeDndPayload` (учтён тип `application/x-kb-tree` в `dataTransfer.types`); **не** вызывается тяжёлый `querySelectorAll` по всему дереву на **каждом** `mousemove` — подсветка зоны сброса обновляется только при смене цели.
- **Сайдбар «Структура»:** зона **«Корень»** с выравниванием **влево**; в одной строке — спиннер и текст статуса. При **загрузке дерева** и при **DnD** (перенос раздела/документа, в т.ч. в корень) в статусе краткие фазы; по успеху — «Готово» (кратко). Отдельный блок `kbTreeLoader` убран — индикатор в строке `kbTreeRootBar`.

## 2026-04-25

### Added

- **Документы (веб + API):** в SQLite у разделов (`collections`) поле `parent_id` (миграция при старте); дерево разделов и документов одним запросом `GET /v1/collections/tree`; агрегированная статистика хранилища `GET /v1/knowledge/stats` (числа сущностей SQLite, размеры `metadata.db`, каталога Chroma, `APP_DATA_DIR`, чанки/эмбеддинги в Chroma); `PATCH /v1/collections/{id}` (имя, родитель), `PATCH /v1/collections/{id}/documents/{doc_id}` (переименование файла в метаданных + Chroma); **`POST /v1/collections/{target_collection_id}/documents/{document_id}/move`** с телом `{ "source_collection_id": "..." }` — перенос документа между разделами (копия чанков в Chroma в целевую коллекцию, затем обновление `documents.collection_id` в SQLite, удаление чанков из исходной коллекции; при `source === target` — no-op); `POST /v1/collections` принимает опциональный `parent_id`; `DELETE /v1/collections/{id}` удаляет поддерево разделов (рекурсия: Chroma + строки БД). Веб-админка: дерево в левом баре на вкладке «Документы», **DnD** (только за handle `⋮⋮`) — перенос разделов (`PATCH` родителя) и документов (`.../move`), зона «Корень» для вывода раздела в корень; сохраняемый порядок соседей **не** хранится (нет `sort_order`), индикаторы above/below/inside лишь задают целевой раздел/родителя; карточки статистики, экран раздела (подразделы, список файлов, загрузка) и экран документа (метаданные, переименование/удаление).
- **Избранные A/B тесты:** каталог `APP_DATA_DIR/tests_favorite/` — JSON-файлы `T000001.json`, …; API `GET/POST /v1/rag-test/favorites`, `GET/DELETE /v1/rag-test/favorites/{id}` (id вида `T` + 6 цифр). Веб-вкладка «Тесты»: кнопка **★ Favorite**, список избранного в левом баре, восстановление слепка и удаление (файл + строка в UI).
- **Тесты RAG (веб):** форма полей `RagRuntimeProfile` (подсказки в `title`), общий блок **«Источники для теста»** (все разделы / выбранные разделы / выбор документов с `document_ids_by_collection`); импорт/экспорт/сохранение профилей по-прежнему как JSON в `localStorage`. Scope тестов независим от области RAG на вкладке «Чат» (`localStorage`: `knowledge_test_scope`).
- **Тесты RAG (A/B):** веб-вкладка «Тесты», API префикс `/v1/rag-test/`: `run`, `compare`, CRUD `profiles`, `main-chat-profile`, `apply-to-chat` (только admin); сохранение прогонов в SQLite (`rag_test_runs`, `rag_test_run_pairs`, `rag_runtime_settings` и др.). `Polza` chat completions: `chat_completion_with_result` возвращает `model` / `provider` / `usage` для диагностики. Основной чат читает safe runtime-overrides из `rag_runtime_settings` (retrieval top-k, temperature, system prompt, distance threshold и т.д.).
- Чат (веб-админка + API): область RAG — **все разделы** (по умолчанию), **один** или **несколько** разделов; retrieval объединяет top‑k по выбранным Chroma-коллекциям. Служебный раздел `__knowledge_rag_all__` в БД для тредов «по всем»; `GET /v1/chat/threads?rag=...` с JSON `{"all":true}` или `{"ids":["..."]}`; `POST /v1/chat/threads` — поле `rag` (альтернатива `collection_id`); у ответа треда — опциональное `rag`.

### Changed

- Веб-админка (`app/static/index.html`): интерактивные состояния (hover/active/focus) для табов, кнопок, списков, полей, чекбоксов/радио, file input, скроллбаров — ближе к рендерам в `app/docs/design`; крупнее иконка настроек в шапке.
- Веб-админка (вкладка **Тесты**): в колонках A/B — кнопка **«Применить к чату»** (`POST /v1/rag-test/apply-to-chat`): текущий профиль той колонки кладётся в **SQLite** `rag_runtime_settings`; основной чат и превью «Основной чат: overrides» в **Настройки** читают снимок с сервера.
- Веб-админка (вкладка **Тесты**): обновлён layout (hero, карточки по carbon_logic), поле вопроса в стиле omnibar; при «Запустить A/B» / «Сравнить A/B» — спиннер и блокировка кнопок до ответа API.
- Веб-админка (чат): цитаты под сообщением ассистента — карточки с текстом и `chunk_id`, не сырой JSON.

### Fixed

- Веб-админка: поля `input[type=number]` на вкладке «Тесты» — убраны CSS-правила к `::-webkit-inner-spin-button`, из-за которых в Chrome стрелки отображались серыми «квадратами».
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

- Режим отладки: заголовок `X-Debug: 1` (переключатель в **Настройках** веб-админки) — `POST /v1/.../chat` пишет на сервер шаги RAG/LLM; при 500 в теле ответа (если `APP_ALLOW_CLIENT_DEBUG` не отключён) — `detail` с `error`, `type`, `trace`. Логи `app`/`app.chat_service` в консоли; `APP_ALLOW_CLIENT_DEBUG` в `app/config.py`, `.env.example`. Audit при сбое логируется, ответ чата не теряется.
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

- `chat_service.run_chat`: при удалённой LLM и ответе «НЕ НАЙДЕНО» с пустыми `citations` локальный fallback добавляет ответ и цитаты только для лексически релевантного retrieval; нерелевантный top-k не маскируется цитатами. System-prompt: не злоупотреблять «НЕ НАЙДЕНО», если фрагменты релевантны.

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
