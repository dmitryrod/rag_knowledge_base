# CONTRIBUTING

## Перед правками

1. Держи секреты только в `app/.env`.
2. Обновляй `app/.env.example`, если меняется набор переменных.
3. Обновляй `app/docs/`, если меняется поведение, конфиг или архитектура: `CHANGELOG.md` при наблюдаемых изменениях; `ARCHITECTURE.md` при новых слоях и потоках данных; `ROADMAP.md` при сдвиге фаз или скоупа; `troubleshooting.md` при повторяющихся сбоях с известным решением.
4. При смене ICP, позиционирования или GTM обновляй `.cursor/marketing-context.md` (канон маркетинга); в `app/docs` достаточно ссылки из `README.md`, если не меняются контракты приложения.

## Окружение Python

- Рекомендуемый способ «как в проде» — **Docker** (`docker compose` в корне, см. `app/docs/README.md`). Репозиторий **не** включает каталог `.venv/`; не коммить его и не требовать от участников.
- Для `pytest`/`pip` локально — любой срез Python, который выбрал разработчик; venv **не** часть стандартного артефакта проекта.
- В Cursor/VSCode, если в новом терминале снова появляется «старое» окружение: **Python: Select Interpreter** (Command Palette) и выбери системный/нужный интерпретатор; в репо задано `python.terminal.activateEnvironment: false` в `.vscode/settings.json` (чтобы терминал не пытался авто-активировать venv).

## Проверка

```bash
python -m pytest app/tests/
```

## Коммиты

Используй Conventional Commits:

```text
feat(scope): short description
```
