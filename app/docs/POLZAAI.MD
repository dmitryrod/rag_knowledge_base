# PolzaAI API

Дата сбора: 2026-04-25.

Практическая справка по PolzaAI API для разработки RAG-чата, embeddings, media и интеграций в текущем проекте. PolzaAI предоставляет OpenAI-compatible REST API. Не коммить реальные API keys.

## Официальная документация

Официальные URL `polza.ai/docs...`, использованные как источник:

### Главное

- <https://polza.ai/docs>
- <https://polza.ai/docs/glavnoe/quickstart>
- <https://polza.ai/docs/glavnoe/faq>
- <https://polza.ai/docs/glavnoe/principles>
- <https://polza.ai/docs/glavnoe/providers>
- <https://polza.ai/docs/glavnoe/enterprise>
- <https://polza.ai/docs/glavnoe/support>

### API Reference

- <https://polza.ai/docs/api-reference/introduction>
- <https://polza.ai/docs/api-reference/chat/completions>
- <https://polza.ai/docs/api-reference/responses/create>
- <https://polza.ai/docs/api-reference/images/generations>
- <https://polza.ai/docs/api-reference/media/create>
- <https://polza.ai/docs/api-reference/media/status>
- <https://polza.ai/docs/api-reference/media/operations>
- <https://polza.ai/docs/api-reference/audio/speech>
- <https://polza.ai/docs/api-reference/audio/transcriptions>
- <https://polza.ai/docs/api-reference/embeddings/create>
- <https://polza.ai/docs/api-reference/models/list>
- <https://polza.ai/docs/api-reference/models/catalog>
- <https://polza.ai/docs/api-reference/other/balance>
- <https://polza.ai/docs/api-reference/history/generations>
- <https://polza.ai/docs/api-reference/storage/upload>
- <https://polza.ai/docs/api-reference/storage/list-files>
- <https://polza.ai/docs/api-reference/storage/get-file>
- <https://polza.ai/docs/api-reference/storage/delete-file>
- <https://polza.ai/docs/api-reference/storage/keep>
- <https://polza.ai/docs/api-reference/storage/stats>

### Гайды

- <https://polza.ai/docs/gaidy/getting-started>
- <https://polza.ai/docs/gaidy/models>
- <https://polza.ai/docs/gaidy/chat-completions>
- <https://polza.ai/docs/gaidy/media-input>
- <https://polza.ai/docs/gaidy/provider-selection>
- <https://polza.ai/docs/gaidy/tool-calling>
- <https://polza.ai/docs/gaidy/structured-output>
- <https://polza.ai/docs/gaidy/web-search>
- <https://polza.ai/docs/gaidy/plugins>
- <https://polza.ai/docs/gaidy/oauth-pkce>

### Model/media guides

- <https://polza.ai/docs/gaidy/gpt-5-image>
- <https://polza.ai/docs/gaidy/gpt-5-image-mini>
- <https://polza.ai/docs/gaidy/gpt-image-1-5>
- <https://polza.ai/docs/gaidy/flux-2-flex>
- <https://polza.ai/docs/gaidy/flux-2-pro>
- <https://polza.ai/docs/gaidy/grok-imagine>
- <https://polza.ai/docs/gaidy/qwen-image>
- <https://polza.ai/docs/gaidy/nanobanano>
- <https://polza.ai/docs/gaidy/nanobanano-2>
- <https://polza.ai/docs/gaidy/nanobanano-pro>
- <https://polza.ai/docs/gaidy/seedream-3>
- <https://polza.ai/docs/gaidy/seedream-4>
- <https://polza.ai/docs/gaidy/seedream-4-5>
- <https://polza.ai/docs/gaidy/seedream-5-lite>
- <https://polza.ai/docs/gaidy/kling-2-5-turbo>
- <https://polza.ai/docs/gaidy/kling-2-6-motion-control>
- <https://polza.ai/docs/gaidy/kling-3>
- <https://polza.ai/docs/gaidy/kling-3-motion-control>
- <https://polza.ai/docs/gaidy/seedance-1-5-pro>
- <https://polza.ai/docs/gaidy/sora-2>
- <https://polza.ai/docs/gaidy/sora-2-pro>
- <https://polza.ai/docs/gaidy/veo-3-1>
- <https://polza.ai/docs/gaidy/wan-2-5>
- <https://polza.ai/docs/gaidy/wan-2-6>
- <https://polza.ai/docs/gaidy/topaz-upscale>
- <https://polza.ai/docs/gaidy/suno-music>
- <https://polza.ai/docs/gaidy/elevenlabs-tts-turbo>
- <https://polza.ai/docs/gaidy/elevenlabs-tts-multilingual>

### Интеграции и особенности

- <https://polza.ai/docs/integracii/claude-code>
- <https://polza.ai/docs/integracii/cline>
- <https://polza.ai/docs/integracii/kilo-code>
- <https://polza.ai/docs/integracii/n8n>
- <https://polza.ai/docs/integracii/opencode>
- <https://polza.ai/docs/integracii/openclaw>
- <https://polza.ai/docs/integracii/roo-code>
- <https://polza.ai/docs/osobennosti/caching>
- <https://polza.ai/docs/osobennosti/reasoning-tokens>
- <https://polza.ai/docs/osobennosti/usage>
- <https://polza.ai/docs/osobennosti/privacy>

Исключено: `https://docs.polza.ai/...`, потому что источник ограничен `polza.ai/docs...`.

## Быстрый старт

Создай API key в dashboard:

```text
https://polza.ai/dashboard/api-keys
```

Ключ показывается один раз. Сохрани его в `app/.env`, не в коде и не в документации.

```env
POLZA_API_KEY=<polza-ai-api-key>
POLZA_BASE_URL=https://polza.ai/api/v1
POLZA_CHAT_MODEL=openai/gpt-4o-mini
POLZA_TEMPERATURE=0
POLZA_CHAT_MODEL_ALLOWLIST=openai/gpt-4o-mini,openai/gpt-4o
ALLOW_LLM_EGRESS=false
```

Auth header:

```http
Authorization: Bearer <POLZA_AI_API_KEY>
```

OpenAI SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://polza.ai/api/v1",
    api_key="<POLZA_AI_API_KEY>",
)
```

Минимальный Chat Completions запрос:

```bash
curl -X POST "https://polza.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o","messages":[{"role":"user","content":"Привет!"}]}'
```

Python:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://polza.ai/api/v1",
    api_key="<POLZA_AI_API_KEY>",
)

response = client.chat.completions.create(
    model="openai/gpt-4o",
    messages=[{"role": "user", "content": "Привет!"}],
)
```

JavaScript:

```js
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://polza.ai/api/v1",
  apiKey: process.env.POLZA_API_KEY,
});

const response = await client.chat.completions.create({
  model: "openai/gpt-4o",
  messages: [{ role: "user", content: "Привет!" }],
});
```

## Base URL и форматы ошибок

Base URL из API introduction:

```text
https://polza.ai/api
```

OpenAI SDK base URL:

```text
https://polza.ai/api/v1
```

HTTP-коды:

- `200`, `201` — успешный ответ;
- `400` — неверный запрос;
- `401` — нет или неверный API key;
- `402` — недостаточно средств;
- `403` — запрещено;
- `404` — ресурс не найден;
- `408` — timeout;
- `429` — rate/usage limit;
- `500`, `502`, `503` — server/provider failure.

Формат ошибки:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Ресурс не найден"
  }
}
```

Обрабатывай ошибку по HTTP-коду и `error.code`; показывай пользователю короткое сообщение, а диагностические детали логируй на сервере.

## Chat Completions

Endpoint:

```http
POST https://polza.ai/api/v1/chat/completions
```

Обязательное поле: `model`.

Передай одно из:

- `messages`;
- `prompt` — PolzaAI преобразует prompt в user message.

Параметры:

- `max_tokens`
- `max_completion_tokens`
- `temperature` от `0` до `2`
- `top_p` от `0` до `1`
- `top_k`
- `frequency_penalty` от `-2` до `2`
- `presence_penalty` от `-2` до `2`
- `stop`
- `seed`
- `n` от `1` до `10`
- `stream`
- `tools`
- `tool_choice`
- `response_format`
- `reasoning`
- `provider`
- `plugins`
- `web_search_options`
- `modalities`
- `audio`
- `user`

Минимальное тело:

```json
{
  "model": "openai/gpt-4o",
  "messages": [
    {
      "role": "user",
      "content": "Привет!"
    }
  ]
}
```

Ответ содержит:

- `id`
- `object: chat.completion`
- `created`
- `model`
- `provider`
- `choices[]`
- `usage`

`usage` включает:

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `cost_rub`
- `cost`

Streaming использует SSE и завершает поток `[DONE]`. Финальный chunk может содержать `usage`.

Для RAG-чата в текущем проекте держи `temperature=0` по умолчанию и включай egress только через `ALLOW_LLM_EGRESS=true`.

## Responses API

Endpoint:

```http
POST https://polza.ai/api/v1/responses
```

Статус: beta. API OpenAI-compatible и внутри преобразуется в Chat Completions.

Обязательные поля:

- `input`
- `model`

Параметры:

- `instructions`
- `metadata`
- `tools`
- `tool_choice`
- `parallel_tool_calls`
- `models`
- `text`
- `reasoning`
- `max_output_tokens`
- `temperature`
- `top_p`
- `top_logprobs`
- `previous_response_id`
- `stream`
- `provider`
- `user`
- `session_id`
- `plugins`

Streaming events:

- `response.created`
- `response.output_item.added`
- `response.content_part.delta`
- `response.content_part.done`
- `response.done`

Используй Chat Completions как основной путь для текущего проекта, потому что существующий конфиг и RAG-чат уже ориентированы на `/chat/completions`.

## Embeddings

Endpoint:

```http
POST https://polza.ai/api/v1/embeddings
```

Обязательные поля:

- `model`
- `input`

Опциональные поля:

- `encoding_format`: `float` или `base64`
- `dimensions`
- `user`

Модели из материалов:

| Model | Размерность |
|-------|-------------|
| `text-embedding-3-large` | `3072` |
| `text-embedding-3-small` | `1536` |

curl:

```bash
curl -X POST "https://polza.ai/api/v1/embeddings" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-3-small","input":["chunk text"]}'
```

Python:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://polza.ai/api/v1",
    api_key="<POLZA_AI_API_KEY>",
)

response = client.embeddings.create(
    model="text-embedding-3-small",
    input=["chunk text"],
)

embedding = response.data[0].embedding
```

Ответ:

- `id`
- `object: list`
- `data[]` с `embedding`, `index`, `model`
- `usage`

Если используешь PolzaAI embeddings для Chroma, фиксируй модель на уровне коллекции и не смешивай размерности. При смене модели переиндексируй коллекции.

## Structured output

Для JSON-ответов используй `response_format` с `json_schema` или `json_object`.

Рекомендованный контракт:

- включай `strict: true`;
- задавай `additionalProperties: false`;
- держи схему маленькой и явной.

Пример формы тела:

```json
{
  "model": "openai/gpt-4o",
  "messages": [
    {
      "role": "user",
      "content": "Верни краткий JSON-ответ."
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "rag_answer",
      "strict": true,
      "schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "answer": { "type": "string" },
          "confidence": { "type": "string" }
        },
        "required": ["answer", "confidence"]
      }
    }
  }
}
```

Не используй structured output для пользовательского Markdown-ответа с цитатами, если UI ожидает обычный текст. Используй его для машинных этапов: классификация запроса, выбор источников, извлечение полей.

## Tool calling

PolzaAI поддерживает OpenAI-style tools:

- `tools` с function schema;
- `tool_choice`: `auto`, `required`, `none` или конкретная function;
- результат инструмента отправляется как message с `role: tool` и `tool_call_id`.

Минимальная форма:

```json
{
  "model": "openai/gpt-4o",
  "messages": [
    {
      "role": "user",
      "content": "Найди документы по теме X."
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_knowledge_base",
        "description": "Search local RAG knowledge base",
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "query": { "type": "string" }
          },
          "required": ["query"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

Для текущего RAG-проекта сначала предпочитай server-side retrieval до LLM. Tool calling пригодится, если модель должна сама выбирать несколько инструментов, но это усложнит аудит и воспроизводимость.

## Web search

Chat Completions использует plugins:

```json
{
  "plugins": [
    {
      "id": "web"
    }
  ]
}
```

Responses API использует tools:

```json
{
  "tools": [
    {
      "type": "web_search_preview"
    }
  ]
}
```

Настройки:

- `max_results`
- `search_prompt`
- `engine`: `native`, `exa`, `auto`
- `enabled`

Аннотации включают sources. В RAG knowledge base не включай web search по умолчанию: он меняет trust boundary с локального контура на внешний поиск.

## Provider routing

Поле `provider` управляет выбором провайдера:

- `order`
- `only`
- `ignore`
- `sort`: `price`, `latency`, `throughput`
- `max_price`
- `allow_fallbacks`

Рекомендация PolzaAI по умолчанию: automatic provider selection.

Для production-режима RAG:

- используй automatic selection, пока нет измерений качества и latency;
- вводи `only` или `ignore` только при конкретной причине;
- логируй `provider` из ответа вместе с `usage`, чтобы объяснять стоимость и нестабильность.

## Images API

Endpoint:

```http
POST https://polza.ai/api/v2/images/generations
```

Обязательные поля:

- `model`
- `prompt`

Параметры:

- `n` от `1` до `10`
- `size`
- `quality`
- `response_format`: `url` или `b64_json`
- `style`
- `output_format`
- `background`
- `output_compression`
- `user`

Sizes:

- `auto`
- `256x256`
- `512x512`
- `1024x1024`
- `1536x1024`
- `1024x1536`
- `1792x1024`
- `1024x1792`

Quality:

- `auto`
- `low`
- `medium`
- `high`
- `standard`
- `hd`

Для нового ПО PolzaAI рекомендует Media API вместо Images endpoint.

## Media API

Endpoint:

```http
POST https://polza.ai/api/v1/media
```

Media API — универсальный API для images/video/audio.

Обязательные поля:

- `model`
- `input`

Опциональные поля:

- `async`
- `user`
- `provider`

Файлы передаются в `images` или `videos` как:

```json
{
  "type": "url",
  "data": "https://example.com/input.png"
}
```

или:

```json
{
  "type": "base64",
  "data": "<base64-data>"
}
```

Статус:

```http
GET https://polza.ai/api/v1/media/{id}
```

Статусы:

- `pending`
- `processing`
- `completed`
- `failed`
- `cancelled`

Polling:

- images: каждые `3-5` секунд;
- video: каждые `5-10` секунд.

Результаты хранятся `7` дней. Для постоянного хранения используй Storage API с `PERMANENT`.

Операции:

```http
POST https://polza.ai/api/v1/media/{id}/operations
```

Поддержанные операции:

- `extend`
- `upscale_1080p`
- `upscale_4k`

Sync ждёт до `120` секунд. Async возвращает operation ID.

## Audio

Text-to-speech:

```http
POST https://polza.ai/api/v1/audio/speech
```

Обязательные поля:

- `input`
- `voice`

Контракты:

- default model: `tts-1`;
- formats: `mp3`, `opus`, `aac`, `flac`, `wav`, `pcm`;
- max input: `5000` символов;
- speed: от `0.25` до `4`.

Speech-to-text:

```http
POST https://polza.ai/api/v1/audio/transcriptions
```

Формат запроса: `multipart/form-data` или JSON.

Обязательное поле:

- `file` как base64, data URL или URL.

Response formats:

- `json`
- `text`
- `srt`
- `verbose_json`
- `vtt`
- `diarized_json`

Поддержанные входные форматы:

- MP3
- WAV
- M4A
- FLAC
- OGG
- WebM

Максимальный размер STT-файла: `25 MB`.

## Models, balance, history

Список моделей:

```http
GET https://polza.ai/api/v1/models
```

API reference говорит, что auth не требуется; guide показывает `Authorization`. В интеграции поддерживай оба сценария: пробуй с Authorization, если ключ настроен.

Filters:

- `type`
- `include_providers`

Types:

- `chat`
- `image`
- `embedding`
- `audio`
- `video`
- `tts`
- `stt`

Catalog:

```http
GET https://polza.ai/api/v1/models/catalog
```

Filters:

- `search`
- `type`
- `inputModalities`
- `outputModalities`
- `providers`
- `contextLengthMin`
- `contextLengthMax`
- `page`
- `limit`
- `sortBy`
- `sortOrder`

Balance:

```http
GET https://polza.ai/api/v1/balance
```

Ответ:

```json
{
  "amount": "9.28591714"
}
```

History:

```http
GET https://polza.ai/api/v1/history/generations
GET https://polza.ai/api/v1/history/generations/{id}
```

Filters:

- `page`
- `limit`
- `dateFrom`
- `dateTo`
- `requestType`
- `status`
- `apiKeyId`
- `withoutApiKey`
- `sortBy`
- `sortOrder`

## Caching и usage

`usage` может показывать:

```text
prompt_tokens_details.cached_tokens
```

Claude поддерживает:

```json
{
  "cache_control": {
    "type": "ephemeral"
  }
}
```

Документация заявляет экономию до `90%`. Типичный минимум prompt для caching: `1000+` tokens. TTL зависит от provider.

Для RAG используй caching осторожно:

- кешируй длинные system/developer инструкции, если provider это поддерживает;
- не кешируй пользовательские секреты и приватные документы без явной политики;
- логируй cached tokens отдельно от total tokens, если считаешь стоимость.

## Лимиты и timeout

- File upload: до `50 MB`.
- Storage image: до `50 MB`.
- Общий timeout: `600` секунд.
- Images endpoint: sync timeout `120` секунд, после чего задача может стать async.
- STT: файл до `25 MB`.
- TTS: input до `5000` символов.

Проектный `MAX_UPLOAD_MB` в `app/.env.example` может быть меньше лимитов PolzaAI. Считай локальный лимит приложения приоритетным.

## Рекомендации для RAG knowledge base

- Держи `POLZA_BASE_URL=https://polza.ai/api/v1`; это OpenAI SDK-compatible путь.
- Оставляй `ALLOW_LLM_EGRESS=false` по умолчанию для локального retrieval-only режима. Включай внешний LLM только осознанно.
- Проверяй `POLZA_CHAT_MODEL` через `POLZA_CHAT_MODEL_ALLOWLIST`, если egress включён.
- Для RAG-ответов используй Chat Completions, `temperature=0`, явный `model` и короткий server-side prompt с цитатами из retrieval.
- Сохраняй `usage.cost_rub`, `usage.cost`, `total_tokens`, `provider` и model в audit/logs, если добавляешь биллинг или диагностику.
- Не включай `plugins: [{"id":"web"}]` по умолчанию: локальный knowledge base должен отвечать по загруженным документам, а не по web.
- Для embeddings через PolzaAI выбери `text-embedding-3-small` или `text-embedding-3-large` один раз на коллекцию Chroma. При смене модели делай переиндексацию.
- Используй provider routing только после измерений. Automatic provider selection проще для MVP.
- Для media/video/audio задач делай async polling и отдельные job states. Не блокируй HTTP-запрос приложения на 600 секунд.
- Для structured output ставь `strict: true` и `additionalProperties: false`, если результат идёт в код, а не напрямую пользователю.
- При `401` проверь `POLZA_API_KEY`; при `402` покажи проблему баланса; при `429` используй retry/backoff; при `5xx` показывай временную недоступность provider/API.
