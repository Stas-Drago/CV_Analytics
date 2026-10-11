# Правила разработки, ревью и деплоя модели

## Базовые правила кода

1. Python 3.11+ целевой минимум после подтверждения совместимости; type hints обязательны для публичных функций и границ I/O.
2. Модуль имеет одну ответственность. API handlers не выполняют YOLO/Ollama/Qdrant напрямую; они вызывают сервисы через интерфейс.
3. Все входные HTTP данные валидировать schema-моделью. Никогда не использовать неявные `request.json.get()` без проверки типа и лимитов.
4. Использовать `pathlib`, `logging`, контекстные менеджеры и UTC-aware `datetime`. Не использовать глобальное mutable state для данных события.
5. SQL только с параметрами и репозиторием; даты не сравнивать как разнородные строки.
6. В UI отображать пользовательские/LLM-данные через `textContent`, не через `innerHTML`.
7. Ошибки внешних сервисов классифицировать (`retryable`/`permanent`), логировать без секретов и возвращать безопасный API error.

## Правила для видео и событий

- Не создавать новый самописный tracker без метрик ID switches и сравнения с выбранным штатным tracker. На одном pipeline — один источник track ID.
- Камера ingest не ждёт LLM: он публикует событие в bounded queue. При полном буфере применяется явная политика sampling/drop и метрика.
- Каждый crop проверять на границы и ненулевой размер. Временные файлы удалять в `finally`; предпочтительна передача bytes, если API позволяет.
- `event_id` генерируется до записи и применяется как idempotency key в DB и Qdrant.
- Не выдавать предположение модели за факт. Сохранять source frame/clip, confidence и версию model/prompt.

## RAG-правила

1. Retrieval: сначала фильтры камеры/времени/типа, затем semantic top-k; top-k и context limit задаются конфигом.
2. Payload Qdrant содержит `event_id`, UTC timestamp, camera_id, type, source URI и нормализованный text. Перед upsert валидировать schema.
3. LLM получает только retrieved evidence. Демонстрационные сценарии не включать в production prompt.
4. Ответ содержит citations (`event_id`, камера, время) или честный отказ при недостатке данных. Никакой классификации «подозрительный» без отдельного правила/модели и human review.
5. Изменение embedding model — только с новым collection/reindex и regression-проверкой retrieval.

## Минимум тестов перед PR

- `ruff check .`, formatter и type check проходят.
- Unit: UTC parsing, bbox/crop, IoU, event idempotency, Markdown/JSON schema, filters, prompt evidence policy.
- Integration с mock Ollama/Qdrant/camera: event → persistence → retrieval → cited answer.
- Regression: UI payload `/makejob` согласован с backend schema; `start_time/end_time` реально фильтруют записи.
- Для любой изменённой модели: фиксированный набор размеченных кадров, метрики precision/recall, ID switches, latency p50/p95 и hallucination/evidence rate.

## Чек-лист code review

- [ ] Нет секретов, адресов камер, персональных данных и токенов в diff/логах.
- [ ] Нет новых import-time side effects, бесконечных потоков или неограниченных очередей.
- [ ] Конфигурация имеет безопасные defaults и явно валидируется.
- [ ] API совместим с UI, имеет schema, status codes, auth и limits.
- [ ] Все внешние вызовы имеют timeout; retry не дублирует событие.
- [ ] RAG-ответ проверяем по первичным событиям.
- [ ] Данные Qdrant/SQLite, модели и generated files исключены из Git.

## Деплой и model release

1. Собрать immutable image с lock-файлом; models/persistent stores — в volumes, не в image layer.
2. Прогнать security scan, unit/integration/evaluation suite в CI.
3. Применить миграции и создать/проверить collection до переключения трафика.
4. Model release содержит: model ID/version/checksum, prompt version, tracker config, evaluation dataset version, метрики и rollback target.
5. Canary на одной тестовой камере; наблюдать backlog, FPS, GPU/CPU/RAM, error rate и качество. Rollback — переключение версии worker/model, без удаления event data.
