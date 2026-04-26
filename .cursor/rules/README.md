# Rules — Оглавление правил `.cursor/rules/`

Большинство правил применяются автоматически (`alwaysApply: true`). Исключения перечислены в таблице. Здесь — краткое описание зачем каждое существует и как связано с агентами/скиллами.

| Файл | Суть | Связанные ассеты |
|------|------|-----------------|
| [`workflow-selection.mdc`](workflow-selection.mdc) | При запросе на реализацию — выбрать workflow (scaffold/implement/feature) и делегировать субагентам через **Task**; задачи дизайна/спеков — через субагента **designer**, не подменять вручную; отдельно — **`/workflow-integrate-skill`** для внешних скиллов (не ломать оркестрацию); маркетинг — агенты **`marketing`** / **`marketing-researcher`** (см. [§ custom-subagent-types](../docs/CREATING_ASSETS.md#custom-subagent-types)); локальная гигиена `.cursor` — [`cursor-sanitize`](../commands/cursor-sanitize.md), [§ local-hygiene](../docs/CREATING_ASSETS.md#local-hygiene) | [`skills/workflow-selector`](../skills/workflow-selector/SKILL.md), [`skills/ecosystem-integrator`](../skills/ecosystem-integrator/SKILL.md), [`commands/workflow-integrate-skill.md`](../commands/workflow-integrate-skill.md), [`commands/cursor-sanitize.md`](../commands/cursor-sanitize.md), [`commands/norissk.md`](../commands/norissk.md), [`agent-intent-map.csv`](../docs/agent-intent-map.csv), [введение к карте](../docs/CREATING_ASSETS.md#agent-intent-map), [§ ecosystem-integrator](../docs/CREATING_ASSETS.md#ecosystem-integrator), [`agents/marketing`](../agents/marketing.md), [`agents/marketing-researcher`](../agents/marketing-researcher.md), [`docs/MARKETING_SKILLS_UPSTREAM.md`](../docs/MARKETING_SKILLS_UPSTREAM.md) |
| [`project-rag-memory.mdc`](project-rag-memory.mdc) | При `/norissk` + фразе про project RAG memory — прочитать `.cursor/active_memory.md` (хук + Chroma/SQLite) | [`.cursor/memory/engine.py`](../memory/engine.py), [`hooks.json`](../hooks.json) |
| [`documentation.mdc`](documentation.mdc) | Когда и что обновлять в `app/docs/`: CHANGELOG, ARCHITECTURE, troubleshooting, .env.example. Google-style docstrings. | [`skills/docs`](../skills/docs/SKILL.md), [`agents/documenter.md`](../agents/documenter.md) |
| [`testing.mdc`](testing.mdc) | Unit/integration/e2e тесты, стиль Arrange-Act-Assert, именование тест-функций | [`agents/test-runner.md`](../agents/test-runner.md) |
| [`security.mdc`](security.mdc) | Базовые требования: секреты в env, валидация входов, параметризованные запросы | [`skills/security-guidelines`](../skills/security-guidelines/SKILL.md), [`agents/security-auditor.md`](../agents/security-auditor.md) |
| [`commit-messages.mdc`](commit-messages.mdc) | Conventional Commits: feat/fix/docs/refactor/chore, scope, 72 символа | [`skills/git-helper`](../skills/git-helper/SKILL.md) |
| [`git-workflow.mdc`](git-workflow.mdc) | Ветки (feature/fix), PR с Closes #N, squash/rebase | [`skills/git-helper`](../skills/git-helper/SKILL.md) |

## Authoring и форматирование (без отдельных `.mdc`)

Сценарии в [`agent-intent-map.csv`](../docs/agent-intent-map.csv): `agent_authoring`, `skill_authoring`, `markdown_normalization`, `capability_architecture`.

- [`skills/agent-creator`](../skills/agent-creator/SKILL.md) — шаблоны агентов и handoff.
- [`skills/agent-skill-creator`](../skills/agent-skill-creator/SKILL.md) — структура скиллов и чеклист.
- [`skills/md-design-system`](../skills/md-design-system/SKILL.md) / [`skills/md-compressor`](../skills/md-compressor/SKILL.md) — формат и opt-in сжатие.
- [`skills/capability-architecture`](../skills/capability-architecture/SKILL.md) — ранний дизайн границ; для ревью кода см. [`skills/architecture-principles`](../skills/architecture-principles/SKILL.md).

## Добавление нового правила

1. Создай `.mdc` файл с frontmatter `description:` и `alwaysApply: true`.
2. Добавь строку в таблицу выше.
3. Если правило связано с агентом/скиллом — обнови их.

Подробнее о создании ассетов: [`docs/CREATING_ASSETS.md`](../docs/CREATING_ASSETS.md). Канон имени инструмента субагентов (`Task`): [`CREATING_ASSETS.md` → «Инструмент Task»](../docs/CREATING_ASSETS.md#task-delegation).
