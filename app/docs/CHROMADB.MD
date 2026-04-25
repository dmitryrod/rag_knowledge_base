# ChromaDB

Дата сбора: 2026-04-25.

Практическая справка для разработки RAG-функций на ChromaDB в этом проекте. Используй как контракт по клиентам, коллекциям, ingest, retrieval и ограничениям. Не храни секреты в документации.

## Официальная документация

Официальные URL `docs.trychroma.com/docs/...`, использованные как источник:

1. <https://docs.trychroma.com/docs>
2. <https://docs.trychroma.com/docs/overview/introduction>
3. <https://docs.trychroma.com/docs/overview/getting-started>
4. <https://docs.trychroma.com/docs/overview/oss>
5. <https://docs.trychroma.com/docs/overview/migration>
6. <https://docs.trychroma.com/docs/overview/troubleshooting>
7. <https://docs.trychroma.com/docs/run-chroma/clients>
8. <https://docs.trychroma.com/docs/run-chroma/client-server>
9. <https://docs.trychroma.com/docs/collections/manage-collections>
10. <https://docs.trychroma.com/docs/collections/add-data>
11. <https://docs.trychroma.com/docs/collections/update-data>
12. <https://docs.trychroma.com/docs/collections/delete-data>
13. <https://docs.trychroma.com/docs/collections/configure>
14. <https://docs.trychroma.com/docs/querying-collections/query-and-get>
15. <https://docs.trychroma.com/docs/querying-collections/metadata-filtering>
16. <https://docs.trychroma.com/docs/querying-collections/full-text-search>
17. <https://docs.trychroma.com/docs/embeddings/embedding-functions>
18. <https://docs.trychroma.com/docs/embeddings/multimodal>
19. <https://docs.trychroma.com/docs/cli/install>
20. <https://docs.trychroma.com/docs/cli/run>
21. <https://docs.trychroma.com/docs/cli/browse>
22. <https://docs.trychroma.com/docs/cli/copy>
23. <https://docs.trychroma.com/docs/cli/db>
24. <https://docs.trychroma.com/docs/cli/login>
25. <https://docs.trychroma.com/docs/cli/profile>
26. <https://docs.trychroma.com/docs/cli/sample-apps>
27. <https://docs.trychroma.com/docs/cli/update>
28. <https://docs.trychroma.com/docs/cli/vacuum>

Не используй эту справку как источник по `/cloud/...`, `/guides/...`, `/integrations/...`, `/reference/...`, GitHub, Discord, X, docs.rs и npm: они не входили в сбор материалов.

## Быстрый старт

Установи Python-пакет:

```bash
pip install chromadb
```

Создай in-memory клиент и коллекцию:

```python
import chromadb

chroma_client = chromadb.Client()
collection = chroma_client.get_or_create_collection(name="my_collection")

collection.upsert(
    documents=[
        "This is a document about pineapple",
        "This is a document about oranges",
    ],
    ids=["id1", "id2"],
)

results = collection.query(
    query_texts=["This is a query document about florida"],
    n_results=2,
)
```

Для TypeScript установи клиент и дефолтные embeddings:

```bash
npm install chromadb @chroma-core/default-embed
npx chroma run --path ./getting-started
```

```ts
import { ChromaClient } from "chromadb";

const client = new ChromaClient();
const collection = await client.getOrCreateCollection({ name: "my_collection" });

await collection.upsert({
  documents: [
    "This is a document about pineapple",
    "This is a document about oranges",
  ],
  ids: ["id1", "id2"],
});

const results = await collection.query({
  queryTexts: ["This is a query document about florida"],
  nResults: 2,
});
```

Всегда задавай `n_results` / `nResults` явно. Значение по умолчанию равно `10`, но явный лимит делает retrieval воспроизводимым.

## Env и конфигурация

Для текущего проекта основной локальный путь задаётся через `APP_DATA_DIR` в `app/.env`. Chroma уже является зависимостью проекта (`chromadb>=0.5.0`) и используется как векторное хранилище.

```env
# Локальные данные приложения: SQLite + Chroma.
APP_DATA_DIR=

# Лимиты chunking/retrieval проекта.
CHUNK_SIZE=800
CHUNK_OVERLAP=120
RETRIEVAL_TOP_K=8
```

Для Chroma Cloud используй только placeholders:

```env
CHROMA_API_KEY=<chroma-cloud-api-key>
CHROMA_TENANT=<tenant-id>
CHROMA_DATABASE=<database-name>
```

Не коммить реальные значения. Если подключаешь cloud-клиент, добавь переменные в `app/.env.example` только в рамках отдельного изменения поведения приложения.

## Клиенты и режимы запуска

Выбирай режим клиента по окружению:

| Режим | Контракт | Пример |
|-------|----------|--------|
| In-memory | Данные живут только в процессе. Подходит для быстрых тестов. | `chromadb.Client()` |
| Persistent | Данные пишутся в локальный путь. Подходит для dev и текущего MVP. | `chromadb.PersistentClient(path="/path/to/save/to")` |
| Server | Chroma запущена отдельным процессом, клиент ходит по HTTP. | `chromadb.HttpClient(host="localhost", port=8000)` |
| Async server | Асинхронный HTTP-клиент. | `client = await chromadb.AsyncHttpClient()` |
| Cloud | Управляемая Chroma с tenant/database/api key. | `chromadb.CloudClient(...)` |

Persistent-клиент по умолчанию использует путь `.chroma`, если `path` не задан. В проекте привязывай путь к `APP_DATA_DIR`, чтобы SQLite и векторные данные жили в одном дереве данных.

```python
import chromadb

client = chromadb.PersistentClient(path="/data/chroma")
```

Запусти серверный режим:

```bash
chroma run --path /db_path
```

Подключись к серверу:

```python
import chromadb

client = chromadb.HttpClient(host="localhost", port=8000)
client.heartbeat()
```

Cloud-клиент:

```python
import chromadb

client = chromadb.CloudClient(
    tenant="<tenant-id>",
    database="<database-name>",
    api_key="<chroma-cloud-api-key>",
)
```

Для TypeScript server options включают `ssl`, `host`, `port`, `database`, `headers`.

`heartbeat()` проверяет соединение. `reset()` полностью очищает базу и является destructive-операцией.

## Коллекции

Имя коллекции:

- длина от 3 до 512 символов;
- начинается и заканчивается lowercase-буквой или цифрой;
- допускает точки, дефисы и подчёркивания;
- не содержит две точки подряд;
- не является валидным IP-адресом;
- уникально внутри database.

Базовые операции:

```python
collection = client.create_collection(name="my_collection")

collection = client.create_collection(
    name="my_collection",
    embedding_function=emb_fn,
    metadata={"description": "my first Chroma collection"},
)

collection = client.get_collection(name="my-collection")
collection = client.get_or_create_collection(name="my-collection")

collections = client.list_collections(limit=100, offset=0)

collection.modify(
    name="new-name",
    metadata={"description": "new description"},
)

count = collection.count()
preview = collection.peek()

client.delete_collection(name="my-collection")
```

Удаление коллекции необратимо. В API проекта не прокидывай raw delete без RBAC и audit.

## Добавление и изменение данных

Передавай `documents`, `embeddings` или оба поля. `metadatas` опциональны. Если переданы только `documents`, Chroma генерирует embeddings через embedding function коллекции.

```python
collection.add(
    ids=["id1", "id2", "id3"],
    documents=["doc1", "doc2", "doc3"],
    metadatas=[
        {"chapter": 3, "verse": 16},
        {"chapter": 3, "verse": 5},
        {"chapter": 29, "verse": 11},
    ],
)
```

Передай embeddings явно, если embedding делается вне Chroma:

```python
collection.add(
    ids=["id1", "id2", "id3"],
    embeddings=[
        [1.1, 2.3, 3.2],
        [4.5, 6.9, 4.4],
        [1.1, 2.3, 3.2],
    ],
    documents=["doc1", "doc2", "doc3"],
)
```

Изменение:

```python
collection.update(
    ids=["id1", "id2"],
    documents=["doc1 updated", "doc2 updated"],
)

collection.upsert(
    ids=["id1", "id3"],
    documents=["updated doc", "new doc"],
)
```

Удаление:

```python
collection.delete(ids=["id1", "id2"])
collection.delete(where={"chapter": "20"})
```

Важные контракты:

- `add` с существующим ID игнорируется без exception; используй `update` или `upsert`, если нужно перезаписать chunk.
- Несовпадение размерности embeddings вызывает exception.
- `update` по отсутствующему ID логирует ошибку и игнорирует запись.
- `delete` необратим.

Для ingest в текущем проекте используй стабильные ID чанков. ID должен быть детерминированным от документа, версии/хеша и номера чанка, чтобы повторный ingest был безопасен через `upsert`.

## Query и get

`query` возвращает результаты, сгруппированные по входному запросу. `get` возвращает плоские массивы. `ids` возвращаются всегда.

```python
results = collection.query(
    query_texts=["thus spake zarathustra"],
    n_results=10,
)
```

Если у коллекции нет embedding function, передавай `query_embeddings`:

```python
results = collection.query(
    query_embeddings=[[11.1, 12.1, 13.1]],
    n_results=100,
    ids=["id1", "id2"],
)
```

Получение документов:

```python
items = collection.get(ids=["id1", "id2"])
items = collection.get(limit=100, offset=0)
```

Фильтрация в query:

```python
results = collection.query(
    query_embeddings=[[11.1, 12.1, 13.1]],
    n_results=100,
    where={"page": 10},
    where_document={"$contains": "search string"},
)
```

Контролируй состав ответа:

```python
results = collection.query(
    query_texts=["my query"],
    include=["documents", "metadatas", "embeddings"],
)

items = collection.get(include=["documents"])
```

Defaults:

- `query` включает `documents`, `metadatas`, `distances`;
- `get` включает `documents`, `metadatas`.

## Metadata filters

Equality shorthand:

```python
{"field": "value"}
```

эквивалентен:

```python
{"field": {"$eq": "value"}}
```

Операторы: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$and`, `$or`, `$in`, `$nin`.

```python
collection.query(
    query_texts=["first query"],
    where={"page": {"$gt": 10}},
)

collection.query(
    query_texts=["first query"],
    where={
        "$and": [
            {"page": {"$gte": 5}},
            {"page": {"$lte": 10}},
        ],
    },
)

collection.get(
    where={
        "$or": [
            {"color": "red"},
            {"color": "blue"},
        ],
    },
)

collection.get(
    where={"author": {"$in": ["Rowling", "Fitzgerald", "Herbert"]}},
)
```

Array metadata:

```python
collection.get(where={"genres": {"$contains": "action"}})
collection.get(where={"genres": {"$not_contains": "action"}})
```

Массивы metadata поддерживают `string`, `int`, `float`, `bool`. Используй один тип элементов в массиве. Не передавай пустые или вложенные массивы.

## Full-text search

`where_document` ищет по тексту документа. Операторы: `$contains`, `$not_contains`, `$regex`, `$not_regex`. Поиск case-sensitive.

```python
collection.get(
    where_document={"$contains": "search string"},
)

collection.get(
    where_document={
        "$regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
    },
)

collection.query(
    query_texts=["query1"],
    where_document={
        "$and": [
            {"$contains": "search_string_1"},
            {"$regex": "[a-z]+"},
        ],
    },
)
```

Для RAG используй full-text search как дополнительный фильтр, а не замену vector retrieval.

## Embedding functions

Дефолтная embedding function использует Sentence Transformers `all-MiniLM-L6-v2` и скачивает модель локально.

```python
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

default_ef = DefaultEmbeddingFunction()
embeddings = default_ef(["foo"])
collection.query(query_embeddings=embeddings)
```

OpenAI embedding function:

```python
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

collection = client.create_collection(
    name="my_collection",
    embedding_function=OpenAIEmbeddingFunction(
        model_name="text-embedding-3-small",
    ),
)
```

Для custom Python embedding function реализуй `EmbeddingFunction`, `__call__`, `name`, `get_config`, `build_from_config` и зарегистрируй через `@register_embedding_function`.

TypeScript embedding packages:

- `@chroma-core/openai`
- `@chroma-core/default-embed`
- `@chroma-core/cohere`
- `@chroma-core/google-gemini`
- `@chroma-core/mistral`
- `@chroma-core/ollama`

## Multimodal

Для изображений используй `OpenCLIPEmbeddingFunction` и `ImageLoader`:

```python
import chromadb
from chromadb.utils.data_loaders import ImageLoader
from chromadb.utils.embedding_functions import OpenCLIPEmbeddingFunction

client = chromadb.Client()
collection = client.create_collection(
    name="multimodal_collection",
    embedding_function=OpenCLIPEmbeddingFunction(),
    data_loader=ImageLoader(),
)

collection.add(
    ids=["id1", "id2"],
    uris=["path/to/file/1", "path/to/file/2"],
)
```

Не смешивай текстовые и image embeddings в одной коллекции без явного решения по модели и размерности.

## HNSW configuration

Настрой HNSW при создании коллекции:

```python
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

collection = client.create_collection(
    name="my-collection",
    embedding_function=OpenAIEmbeddingFunction(
        model_name="text-embedding-3-small",
    ),
    configuration={
        "hnsw": {
            "space": "cosine",
            "ef_construction": 200,
        },
    },
)
```

Фиксируй `space` до ingest. Не меняй метрику на существующей коллекции без миграции и переиндексации.

## CLI и Docker

Локальный сервер:

```bash
chroma run --path /db_path
```

Сервер через npm:

```bash
npx chroma run --path ./getting-started
```

Docker:

```bash
docker pull chromadb/chroma
docker run -p 8000:8000 chromadb/chroma
```

Конфигурация:

```bash
chroma run --config ./config.yaml
```

Cloud/login и database:

```bash
chroma login
chroma login --profile my_profile_name --api-key ck-...
chroma db create chroma-getting-started
chroma db connect chroma-getting-started --env-file
chroma db connect chroma-getting-started --env-vars
```

Не вставляй реальный API key в shell history, если можно использовать env-файл или секрет-хранилище.

## Ограничения и подводные камни

- Требуется SQLite `3.35+`.
- In-memory клиент теряет данные после завершения процесса.
- `client.reset()` полностью очищает DB. Для `PersistentClient` reset может требовать `Settings(allow_reset=True)`.
- `add` не перезаписывает существующий ID.
- Dimension mismatch embeddings ломает операцию exception.
- `query` возвращает column-major grouped arrays по input query; не обрабатывай результат как плоский список.
- `where_document` case-sensitive.
- Array metadata не поддерживает пустые, вложенные и смешанные по типу массивы.
- Next.js с JS default embedding может требовать `withChroma` из-за bundling `@huggingface/transformers`.
- Rust client требует передавать embeddings напрямую.

## Рекомендации для RAG knowledge base

- Храни Chroma под `APP_DATA_DIR`, рядом с SQLite-метаданными. Это упрощает backup, перенос dev-окружения и docker volume.
- Используй одну коллекцию Chroma на раздел знания, как описано в `ARCHITECTURE.md`: это сохраняет простую RBAC-модель и позволяет `query_multi` объединять top-k по выбранным разделам.
- Делай ID чанка детерминированным: `<document_id>:<version_or_hash>:<chunk_index>`. Повторный ingest выполняй через `upsert`.
- Пиши в metadata только фильтруемые поля: `collection_id`, `document_id`, `page`, `chunk_index`, `source_name`, `content_hash`. Не клади туда большие тексты.
- Задавай `RETRIEVAL_TOP_K` явно и передавай `n_results` явно в каждом query.
- Не вызывай `reset()` из production-кода. Для тестов изолируй временный `APP_DATA_DIR`.
- При смене embedding model создай новую коллекцию или переиндексируй существующую. Не смешивай размерности в одной коллекции.
- Для ответов с цитатами всегда сохраняй связь chunk → document/page/source в metadata, иначе LLM-слой не сможет корректно объяснить происхождение ответа.
- Для cloud-режима вводи отдельный конфиг и allowlist операций. Не меняй локальный persistent default без миграционного плана.

## Практики из GitHub-проектов

Дата исследования: 2026-04-25.

### Исследованные GitHub-ссылки

Официальные источники ChromaDB:

1. <https://github.com/chroma-core/chroma>
2. <https://github.com/chroma-core/chroma/blob/main/docker-compose.yml>
3. <https://github.com/chroma-core/chroma/blob/main/docker-compose.server.example.yml>
4. <https://github.com/chroma-core/chroma/tree/main/examples>
5. <https://github.com/chroma-core/chroma/tree/main/examples/basic_functionality>
6. <https://github.com/chroma-core/chroma/tree/main/examples/deployments>
7. <https://github.com/chroma-core/chroma/issues/2274>
8. <https://github.com/chroma-core/chroma/issues/2446>
9. <https://github.com/chroma-core/chroma/issues/4368>
10. <https://github.com/chroma-core/chroma/issues/4089>

Публичные RAG-примеры и приложения:

1. <https://github.com/yussufbiyik/langchain-chromadb-rag-example>
2. <https://github.com/Danielskry/LangChain-Chroma-RAG-demo-2024>
3. <https://github.com/jodog0412/rag-chatbot-app-with-fastapi>
4. <https://github.com/Zlash65/rag-bot-fastapi>
5. <https://github.com/box-community/Box-RAG-Workshop>
6. <https://github.com/crd/logseq-chat>
7. <https://github.com/schoolofdevops/lightweight-genai-stack>
8. <https://github.com/open-webui/open-webui>
9. <https://github.com/BittnerPierre/applied-ai-rag-assistant>

### Повторяющиеся практики

- Для прототипов допустим `chromadb.Client()`, но для RAG-данных используй `PersistentClient(path=...)`, LangChain `persist_directory` или отдельный Chroma HTTP service.
- В Docker обязательно монтируй volume под директорию Chroma. В официальных compose-примерах используется volume для `/data` или `/chroma/chroma`, а в прикладных проектах часто встречается `./chroma_db:/app/.../chroma_db`.
- Для production-like режима предпочитай отдельный `chromadb` service и `HttpClient`, если несколько процессов или приложений должны обращаться к одной базе.
- Не смешивай embeddings разных моделей в одной коллекции. Разделяй коллекции или persist paths по `embedding_model`, provider, dimension и версии ingest-схемы.
- Храни имя/версию embedding model рядом с конфигурацией коллекции: `text-embedding-ada-002`, `nomic-embed-text`, `all-MiniLM`, `BAAI/bge-base-en-v1.5`.
- Используй стабильные IDs и `upsert`, если ingest может повторяться. Для LangChain-примеров, где вызывается только `add_documents`, нужен отдельный слой дедупликации.
- Metadata должна быть маленькой и фильтруемой: `source`, `title`, `basename`, `dir`, `tags`, `page`, `chunk_index`, `document_id`. Большой текст, страницы, таблицы и raw-структуры не клади в metadata.
- Фильтры работают лучше на небольших нормализованных scalar-полях. Для очень больших коллекций проверяй latency фильтров отдельно.
- Делай ingest батчами. В крупных приложениях встречается batching через `chromadb.utils.batch_utils.create_batches`; без batching легко получить высокий memory pressure.
- Для тестов используй временный persist path и cleanup после теста. Не удаляй persist directory, пока жив процесс Chroma или объект клиента.
- Для диагностики добавь команды/скрипты: count коллекции, список источников, sample similarity query, проверка metadata, проверка embedding model.
- Для Chroma HTTP/Cloud фиксируй auth-настройки явно: host, port, ssl, tenant, database, headers/auth credentials. Не считай HTTP endpoint защищённым без отдельной проверки.
- Для migration/reindex заводи новую коллекцию или новый persist path, прогоняй ingest заново, проверяй counts и sample queries, затем переключай retrieval.

### Антипаттерны и частые проблемы

- Не используй in-memory client для данных, которые должны пережить рестарт.
- Не запускай `reset`, `delete_collection`, `clear_database_on_start` и `docker compose down -v` против production-данных.
- Не коммить `chroma.sqlite3`, `data_level0.bin`, `header.bin`, `length.bin`, `link_lists.bin` и другие файлы persist-dir в git. Persist-dir должен быть volume, backup artifact или локальная runtime-директория.
- Не меняй embedding model для существующей коллекции без reindex. Ошибка вида `InvalidDimensionException: Embedding dimension 384 does not match collection dimensionality 768` означает смешение размерностей.
- Не полагайся на автоматическую загрузку embedding-моделей внутри контейнера без cache/volume и offline-плана. Иначе cold start может зависеть от сети и доступности HuggingFace/Ollama.
- Не складывай большие documents, tables, pages, sections и raw JSON в metadata. В крупных приложениях такие поля фильтруют перед записью в Chroma.
- Не удаляй persist directory из другого процесса, пока Chroma используется приложением. В issues ChromaDB встречается `PermissionError` на `data_level0.bin` при попытке `shutil.rmtree`.
- Не оставляй Chroma HTTP endpoint без auth/network restrictions. Проверяй фактическим запросом без credentials, что endpoint не отдаёт данные.
- Не считай SQLite/HNSW maintenance автоматической. После апгрейдов Chroma может требовать `chroma vacuum`; в Docker-образах приложений CLI может отсутствовать.
- Не делай unbounded ingestion. Ограничивай типы файлов, размер, количество chunks, batch size и concurrency.

### Рекомендации для этого проекта

- Вынеси путь Chroma в config/env, например `CHROMA_PERSIST_DIR`, и не привязывай production path к текущей рабочей директории.
- Для локального embedded режима используй отдельную runtime-директорию под `app/` или volume; добавь её в `.gitignore`.
- Для Docker режима монтируй volume под persist path и документируй backup/restore на уровне volume/directory.
- В коллекцию добавляй metadata schema минимум: `source`, `document_id`, `chunk_id`, `chunk_index`, `content_hash`, `embedding_model`, `embedding_dimension`, `ingest_version`.
- Генерируй deterministic IDs из `document_id + chunk_index + content_hash` и используй `upsert`, чтобы повторный ingest не плодил дубликаты.
- При смене chunking, metadata schema или embedding model создавай новую коллекцию с версией в имени, например `docs_v2`, и выполняй reindex.
- Для retrieval поддерживай `where`-фильтры только по коротким scalar-полям. Не проектируй фильтрацию по произвольной большой metadata.
- Добавь smoke-check после ingest: `collection.count()`, выборка по одному `document_id`, один query с `include=["documents", "metadatas", "distances"]`.
- Для тестов создавай временный Chroma path через temp directory и удаляй его только после закрытия тестового сценария.
- Для Chroma HTTP режима добавь env: `CHROMA_HTTP_HOST`, `CHROMA_HTTP_PORT`, `CHROMA_HTTP_SSL`, `CHROMA_TENANT`, `CHROMA_DATABASE`, `CHROMA_AUTH_TOKEN` или headers.
