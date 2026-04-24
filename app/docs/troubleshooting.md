# Troubleshooting

## Симптом

В браузере: `ERR_CONNECTION_REFUSED` при открытии API; или открыт не тот порт (ожидали 8000, в Docker обычно 8002).

## Причина

Процесс не слушает порт, или в адресной строке **другой порт**, чем в `docker compose` (см. `KNOWLEDGE_API_PORT` / вывод в терминал при старте: `Open: http://127.0.0.1:…`).

## Шаги

1. Убедись, что контейнер/uvicorn запущен: `docker ps` или окно с `knowledge-api` / `uvicorn` без трейсбэка.  
2. Открой URL из лога старта: корень **`/`** — веб-админка; **`/docs`** — Swagger; **`/v1/health`** — health. Порт с хоста (часто 8002), не путай с 8000.  
3. Для Compose по умолчанию хост-порт **8002**, не 8000. Проверка: `docker compose port knowledge-api 8000` → `0.0.0.0:8002` (пример).

## Как проверить

`curl http://127.0.0.1:8002/v1/health` (с подставленным портом) отдаёт JSON `ok`.

---

## Симптом

`docker compose up --build` / `docker build` падает с `DeadlineExceeded` / `context deadline exceeded` при шаге **load metadata** для образа с `registry-1.docker.io` (например `python:3.12-slim-bookworm`).

## Причина

Нет стабильного доступа к **Docker Hub** с хоста (медленный/обрывистый интернет, DNS, файрвол, прокси, VPN, региональные ограничения, rate limit). К **Dockerfile приложения** это не привязано: падает именно **pull манифеста/образа**.

## Шаги

1. **Сразу сработает без Hub**, если образ уже в Docker: `docker image ls` — есть `python` `3.12-slim-bookworm`. Если нет — `.\scripts\docker-ensure-base-image.ps1` (подхватит `local-dist\docker\python-3.12-slim-bookworm.tar`, если скопировал) или сначала `docker pull`, когда сеть есть.  
2. Запуск одной командой: `.\scripts\compose-up.ps1` (тот же `docker compose up --build` после проверки образа).  
3. Проверь отдельно: `docker pull python:3.12-slim-bookworm` — если снова таймаут, проблема в сети/доступе к Hub.  
4. Повтори сборку позже или с другой сетью / VPN.  
5. Windows: DNS `8.8.8.8` / `1.1.1.1` на адаптере, `ipconfig /flushdns`.  
6. Docker Desktop: **Settings → Resources / Network** — прокси/зеркало.  
7. **Локальный кэш образа:** `.\scripts\refresh-local-dist.ps1 -IncludeDockerBase` (на машине, где Hub доступен) → `local-dist\docker\python-3.12-slim-bookworm.tar` → на этой машине `.\scripts\docker-ensure-base-image.ps1` или `docker load -i ...`. Для pip **без PyPI** в build: `Dockerfile.wheels` + `docker-compose.wheels.yml` и `local-dist\wheels` (см. `README.md`).  
8. Без Docker: `uvicorn` / `knowledge-api` — `README.md`.

## Как проверить

`docker pull python:3.12-slim-bookworm` завершается без ошибки; затем `docker compose build` проходит шаг `FROM`.

---

## Симптом

С `ALLOW_LLM_EGRESS=true` в ответе «НЕ НАЙДЕНО В БАЗЕ» и пустой `citations`, а с `false` демо-ответы с цитатами из retrieval были.

## Причина

Раньше при ответе модели с фразой «НЕ НАЙДЕНО…» и пустом JSON `citations` **не подставлялись** цитаты из топа Chroma (в отличие от режима без LLM). Плюс строгий system-prompt провоцировал ложные «не найдено», хотя релевантные чанки в контексте были.

## Шаги

1. Обнови `app/chat_service.py` (после фикса): при ненулевом retrieval пустые citations от LLM дополняются фрагментами из индекса; prompt смягчён.  
2. Убедись, что в разделах есть проиндексированные документы и вопрос не пустой.  
3. Проверь `POLZA_CHAT_MODEL` и при заданном `POLZA_CHAT_MODEL_ALLOWLIST` — модель должна входить в список.

## Как проверить

`python -m pytest app/tests/test_chat_service.py -q` — сценарий с моком LLM и «НЕ НАЙДЕНО» должен давать непустые citations.

---

## Симптом

`NewConnectionError` / `[Errno 11001] getaddrinfo failed` к `files.pythonhosted.org` или `pypi.org` при `pip install` (после отключения прокси те же ошибки остаются).

## Причина

На **хосте** не разрешается DNS или нет исходящих соединений (Wi‑Fi/адаптер, корпоративный `hosts`, трекер, VPN, сломанные DNS). К **коду `app/`** это не относится. Сборка `docker compose build` тянет пакеты **из сети Docker** — иногда сеть в контейнерах работает, когда на хосте `pip` падает; если и там `getaddrinfo`, почини DNS/маршрут или используй **offline** wheels.

## Шаги

1. `ping pypi.org` / открытие `https://pypi.org` в браузере с той же машины.  
2. `ipconfig /flushdns` (Windows), смена DNS на 8.8.8.8/1.1.1.1 в адаптере при необходимости.  
3. Повтори `python -m pip install -U pip setuptools wheel` — если не нужен upgrade pip, `pip show setuptools` (уже в текущем окружении достаточно) и `pip install -e . --no-build-isolation`.  
4. Альтернатива: `docker compose up --build` из корня (порты см. `README`, порт хоста по умолчанию 8002).

## Как проверить

`nslookup pypi.org` возвращает адреса; `pip index versions setuptools` сходится без `getaddrinfo failed`.

---

## Симптом

`python -m pytest app/tests/` падает из-за отсутствующего окружения или зависимостей.

## Причина

Python toolchain ещё не создан локально или не подтянуты зависимости из `pyproject.toml`.

## Шаги

1. Убедись, что установлен Python 3.11+.
2. Запусти `python -m pytest app/tests/` из корня workspace.
3. Если `pytest` недоступен, установи зависимости из `pyproject.toml`.

## Как проверить

Команда `python -m pytest app/tests/` завершается без ошибок и smoke-test проходит.

---

## Симптом

В тестах FastAPI: `RuntimeError: Stores not initialized` при вызове эндпоинтов, которые используют `deps.get_db()`, хотя `GET /v1/health` проходит.

## Причина

`TestClient` без контекстного менеджера не отправляет событие `lifespan`, поэтому `init_stores` не выполняется.

## Шаги

1. Оборачивай клиент: `with TestClient(create_app()) as client:` и `yield client` в фикстуре.

## Как проверить

Запросы к защищённым маршрутам после старта теста не падают с `Stores not initialized`.

---

## Симптом

`pip install -e .` падает с `ReadTimeoutError` к `pypi.org` и далее `Could not find a version that satisfies the requirement setuptools` / `from versions: none`.

## Причина

Нет стабильного доступа к PyPI (таймаут, файрвол, провайдер, блокировка). Сообщение про `setuptools` — следствие: индекс не загрузился, pip не видит ни одной версии.

## Шаги

1. Проверь доступ: браузер или `curl -I https://pypi.org/simple/` с той же машины.
2. Увеличь таймаут и повтори:  
   `pip install --default-timeout=120 -e .`
3. Если нужен прокси: задай `HTTP_PROXY` / `HTTPS_PROXY` или настрой `pip config set global.proxy ...`.
4. После того как сеть к PyPI есть, обнови инструменты сборки:  
   `python -m pip install -U pip setuptools wheel`  
   затем снова `pip install -e .`
5. Если `setuptools` уже установлен в текущем окружении Python, можно обойти изолированную сборку (только если понимаешь риски):  
   `pip install -e . --no-build-isolation`

## Как проверить

`pip install -e .` завершается без ошибок; `python -c "import app.main"` из корня workspace работает.

---

## Симптом

`ProxyError` / `407 Proxy Authentication Required` при `pip install`; в логе сначала может быть `Installing build dependencies` и `Could not find a version that satisfies the requirement setuptools>=61.0 (from versions: none)`; либо `pip install -e . --no-build-isolation` падает с `BackendUnavailable: Cannot import 'setuptools.build_meta'`.

## Причина

1. В окружении задан `HTTP(S)_PROXY` без корректной аутентификации (или с неверной) — **любой** шаг pip к PyPI, в том числе **изолированная сборка** (отдельный субпроцесс качает `setuptools`), получает 407. Сообщение «versions: none» — следствие: индекс не загружен, а не «нет setuptools в природе».
2. Пока 407 не устранён, не установятся и **зависимости проекта** (FastAPI, ChromaDB и т.д.) — исправлять надо доступ к PyPI целиком, а не только `pyproject.toml`.
3. Если PyPI уже доступен, а падает только этап **build dependencies**: в текущем окружении поставь `setuptools` и `wheel`, затем `pip install -e . --no-build-isolation` (или `scripts\pip-install-editable.ps1` из корня репозитория) — тогда бэкенд сборки не качается в отдельное изолированное окружение.
4. `Cannot import 'setuptools.build_meta'` — в этом интерпретаторе Python **нет** установленного **setuptools**; сначала п. 1–3, потом снова установка.

## Шаги

1. В PowerShell на сессию сбросить прокси, если прямой доступ к PyPI разрешён: `Remove-Item Env:HTTPS_PROXY, Env:HTTP_PROXY, Env:ALL_PROXY -ErrorAction SilentlyContinue`.
2. Или задать рабочий прокси с учёткой: `https://USER:PASSWORD@host:port` (или внутренний mirror PyPI по политике ИБ) и для pip: `python -m pip config set global.proxy ...` при необходимости.
3. Когда `python -m pip install -U pip setuptools wheel` проходит, из корня репозитория: `pip install -e .` **или** при повторяющемся сбое только на build isolation: `pip install -e . --no-build-isolation` / `.\scripts\pip-install-editable.ps1`.
4. Затем `pip install -e .` дотянет остальные зависимости из `[project] dependencies` — и здесь снова нужен тот же рабочий доступ к индексу, что и в п. 3.

## Как проверить

`python -c "import setuptools; print(setuptools.__version__)"` выполняется без ошибки; `pip install -e .` завершается успешно; `python -c "import app.main"` из корня workspace работает.

---

## Симптом

В логе приложения или в ответе API (раньше 500): `ConnectError: [Errno -3] Temporary failure in name resolution` при вызове Polza/LLM (`httpx` в `app/llm.py`); в UI чат падает с ошибкой сети.

## Причина

Хост из `POLZA_BASE_URL` не удаётся разрешить через DNS в среде запуска (часто **контейнер Linux + сломанный/пустой resolv** на хосте, VPN, корпоративные DNS, или **опечатка/неверный URL** в `app/.env`).

## Шаги

1. С хоста: `nslookup` / `ping` к хосту из `POLZA_BASE_URL` (например `polza.ai`) — сравни с тем же **внутри контейнера**: `docker exec -it marketing-product-knowledge-api getent hosts polza.ai` (или `nslookup` если есть в образе).
2. Проверь `POLZA_BASE_URL` в `app/.env`: схема `https://`, без лишних пробелов, тот хост, который реально доступен из сети приложения.
3. Docker (`docker-compose.yml`): добавлен `dns: 8.8.8.8` / `8.8.4.4` — пересобери/перезапусти. Если политика требует **внутренний DNS**, убери публичные DNS и укажи свои `dns:` в `docker-compose` или `daemon.json` Docker.
4. Сетевой доступ: контейнер должен мочь сходить в интернет (или в корпоративный forward/proxy) до провайдера API.

## Как проверить

После шагов: тот же запрос к `POST /v1/.../chat` возвращает 200, либо при недоступности шлюза — **502** с текстом «Не удаётся подключиться к LLM…», а не сырой traceback (для 502 `detail` — строка).

---

## Симптом

В консоли браузера: `TypeError: Failed to fetch` при открытии веб-админки, Health не грузится, чат не шлёт запросы.

## Причина

1. **CORS**: страница с одного `Origin` (другой порт, `file://`, другой хост), API — с другого; браузер блокирует `fetch` до ответа.  
2. **Неверный base URL**: UI ходит не на тот хост/порт (см. `APP_PUBLIC_BASE_URL`).

## Шаги

1. Включи CORS: по умолчанию в `app/main.py` уже **`*`** через `APP_CORS_ORIGINS`; при узком списке укажи точный `Origin` из DevTools → Network (схема+хост+порт).  
2. UI и API с одного происхождения: открой `http://127.0.0.1:ПОРТ/` (тот порт, что в `docker compose` / uvicorn), не `file://` и не соседний порт Live Server без прокси.  
3. Если UI статически с другого URL — задай `APP_PUBLIC_BASE_URL` = полный base API (`http://…:8002` без слеша в конце) и **разреши** этот `Origin` в `APP_CORS_ORIGINS` (либо `*` в dev).

## Как проверить

`curl -sI -X OPTIONS "http://127.0.0.1:8002/v1/health" -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET"` — в ответе есть `access-control-allow-origin` (для `*` — `*`).
