---
name: workflow-selector
description: Use when implementing features. Analyze task complexity and choose workflow-scaffold/workflow-implement/workflow-feature. Apply when user asks to add, create, or implement something.
---

# Workflow Selector

При запросе на реализацию (добавить, создать, реализовать) — оцени сложность задачи и выбери один из трёх workflow.

## Ранний branch: marketing vs engineering

Перед выбором workflow проверь **тип результата**:

- Если пользователь просит **маркетинговый deliverable** (headline, CTA, landing copy, email sequence, CRO-аудит, SEO-план, соцконтент, launch asset) — сначала сверься с [`agent-intent-map.csv`](../../docs/agent-intent-map.csv) и запускай **`Task(subagent_type="marketing", ...)`**, а не `worker`.
- Если пользователь просит **маркетинговое исследование / GTM** (ICP, positioning, full marketing plan, launch strategy, pricing research) — сначала запускай **`Task(subagent_type="marketing-researcher", ...)`**.
- Только если задача реально про код/структуру/доки в `app/` или инженерный ассет в `.cursor/`, выбирай `workflow-scaffold` / `workflow-implement` / `workflow-feature`.

## Ранний branch: authoring `.cursor/` (агенты, скиллы, md)

Если запрос про **новый агент**, **новый скилл**, **нормализацию Markdown** или **capability / границы модулей** — смотри строки `agent_authoring`, `skill_authoring`, `markdown_normalization`, `capability_architecture` в [`agent-intent-map.csv`](../../docs/agent-intent-map.csv); скиллы [`agent-creator`](../agent-creator/SKILL.md), [`agent-skill-creator`](../agent-skill-creator/SKILL.md), [`md-design-system`](../md-design-system/SKILL.md), [`capability-architecture`](../capability-architecture/SKILL.md). Обычно `scaffold` или `implement`; внешний пакет — **`/workflow-integrate-skill`**.

## Ранний branch: local hygiene (сессии / кэш)

Если пользователь просит **почистить `.cursor`**, **санитаризацию**, **удалить кэш сессий** или **reset cursor local state** — смотри строку **`cursor_hygiene`** в [`agent-intent-map.csv`](../../docs/agent-intent-map.csv) и команду [`cursor-sanitize`](../../commands/cursor-sanitize.md): **`Task(subagent_type="worker", ...)`** запускает [`sanitize-cursor.mjs`](../../scripts/sanitize-cursor.mjs) (сначала `--dry-run`). Это **не** обычная реализация кода; тест-раннер обычно не нужен.

## Ранний branch: усиление промпта (advisory-only)

Если явно просят **улучшить/оптимизировать промпт**, **переписать prompt** или **как лучше попросить Cursor** — смотри строку **`prompt_enhancement`** в [`agent-intent-map.csv`](../../docs/agent-intent-map.csv) и агент [`prompt-enhancer`](../../agents/prompt-enhancer.md): **`Task(subagent_type="prompt-enhancer", ...)`** готовит вставляемый текст и маршрут, **без** выполнения исходной задачи. Если вместо рерайта пользователь просит «просто сделай/реализуй» — не подменяй: выбери workflow по смыслу задачи, как в остальных строках CSV.

## Критерии выбора

| Workflow | Когда выбирать |
|----------|---------------|
| **workflow-scaffold** | Один артефакт (функция, компонент, эндпоинт); мало зависимостей; нет auth/payments/sensitive data; задача укладывается в 1–3 файла |
| **workflow-implement** | Несколько связанных файлов; нужен code review; средняя сложность; не требует декомпозиции на подзадачи; 4–10 файлов |
| **workflow-feature** | Auth, payments, sensitive data; много подзадач; нужна декомпозиция; архитектурные решения; интеграция нескольких подсистем |
| **workflow-integrate-skill** | Не фича в `app/`, а расширение тулчейна: внешний скилл / best practices из skills.sh в `.cursor/` с адаптацией под **Task** — см. [`ecosystem-integrator`](../ecosystem-integrator/SKILL.md) и команду `/workflow-integrate-skill` |

## Шаги каждого workflow (команды: /workflow-scaffold, /workflow-implement, /workflow-feature, /workflow-integrate-skill)

**workflow-scaffold:** при необходимости designer (дизайн-only: designer → documenter; или designer перед worker) → worker → test-runner → documenter

**workflow-implement:** при необходимости designer → worker → test-runner → reviewer-senior → documenter (ветка только дизайн: designer → documenter)

**workflow-feature:** planner (brainstorming → план по скиллам) → [designer / worker / refactor по плану] → test-runner → reviewer-senior → security-auditor (если security-sensitive) → documenter

**marketing_tactical (по CSV):**
- без свежих веб-фактов: `marketing`
- если нужны актуальные конкурентные / рыночные данные: `researcher` → `marketing`

**marketing_research (по CSV):** marketing-researcher → researcher (по необходимости) → marketing (для конечных тактических артефактов после roadmap)

## Делегирование

Шаги выполняются через вызов **Task** с subagent_type. Не выполняй роли субагентов сам — только делегируй через Task.

## Эскалация

Если в процессе выполнения задача оказалась сложнее выбранного workflow — переключись на следующий. **Триггеры эскалации:**
- scaffold → implement: появились связанные изменения, нужен review, затронуто >3 файлов
- implement → feature: появились подзадачи, нужна декомпозиция, нужен security-auditor (auth/payments/sensitive data)

**При эскалации** передай субагенту: выбранный workflow, что уже сделано, текущие блокеры. Максимум одна эскалация за сессию — при повторной необходимости сообщи пользователю.

## При неопределённости

Склоняйся к более полному workflow: workflow-implement лучше workflow-scaffold, workflow-feature лучше workflow-implement.

## Примеры

- `Напиши 5 вариантов headline + CTA для лендинга` → `Task(subagent_type="marketing", ...)`
- `Исследуй рынок и собери GTM для нового продукта` → `Task(subagent_type="marketing-researcher", ...)`
- `Добавь кнопку экспорта в PDF` → `workflow-scaffold`
