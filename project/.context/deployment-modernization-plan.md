# Деплой, модернизация и утверждение кода

## Реализовано в каркасе

- FastAPI entrypoint без запуска камер, регистрации и моделей при import.
- PostgreSQL-ready event schema, Redis bounded queue abstraction, Qdrant/MinIO контейнерные сервисы.
- Docker Compose: API, PostgreSQL, Redis, Qdrant, MinIO и Nginx с обязательными TLS-сертификатами.
- Самописная PyTorch `DangerMLP` (LaBSE 768 → 256 → 64 → 3) и offline training script.
- UCA manifest, risk policy, model card, `.env.example`, dependency lock и тесты базовых invariants.

## Порядок включения в окружении

1. Получить юридическое подтверждение условий UCA и сохранить checksum/версию набора в manifest.
2. Создать защищённый `.env`, TLS-certificate, private Docker network и persistent backups volumes.
3. Импортировать валидированный training JSONL в `data/raw/` (не Git), выполнить split по `source_video`, обучить модель и выпустить model card с метриками.
4. Прогнать API/integration/load/security тесты в staging без реальных камер.
5. Подключить одну тестовую камеру в shadow mode: риск записывается, но не уведомляет оператора.
6. После формального acceptance включить UI-уведомления для `high`; автоматические действия остаются запрещёнными.

## Обязательные approval gates

| Gate | Кто подтверждает | Критерий |
|---|---|---|
| Data/legal | владелец данных и юрист | Условия UCA, privacy, retention и доступ к видео утверждены |
| Security | security owner | Secrets не в Git, TLS/RBAC/rate limit, dependency/SAST scan без блокирующих находок |
| Code | 2 reviewers | CI, schema/API contract, migration/rollback и test coverage одобрены |
| Model | ML owner + security operator | Held-out metrics, recall high, calibration, русская валидация и model card утверждены |
| Operations | platform owner | Backup/restore, health checks, 24h soak, canary и rollback проверены |

## Минимальные acceptance tests

- Event с одинаковым `event_id` не создаёт дубликат.
- Медленная/недоступная model service не останавливает ingest и наблюдаемо заполняет очередь.
- Все RAG-ответы с фактическим утверждением содержат event ID, время и камеру.
- `high` создаёт pending alert; только оператор меняет его на confirmed/rejected.
- Ни камера, ни журнал, ни alerts не доступны без внутренней аутентификации (добавляется до production activation).

## Включение Query Router (Этап 5)

1. Запустить Compose-сервисы PostgreSQL, Redis и Qdrant; применить `scripts/apply_migrations.py` (добавляет `analytics_events` и `query_audit_log`).
2. В защищённом `.env.host` задать уникальный `POSTGRES_READER_PASSWORD`; выполнить `python scripts/provision_analytics_reader.py` с административным `DATABASE_URL`.
3. Контролируемо создать только payload-indexes новой Qdrant collection: `scripts/run_query_worker.sh --ensure-qdrant-indexes`. Эта команда не запускает backfill и сначала проверяет размерность 768 / Cosine.
4. Запустить host-only worker: `scripts/run_query_worker.sh`. Он использует Redis consumer group и не открывает сетевой порт.
5. Проверить `POST /api/query` общим вопросом и количественным вопросом с периодом. Вопрос без периода должен вернуть `422 clarification_required`; недоступный worker — `503`, превышение ожидания — `504`.

Запрещены любые fallback-подключения reader-worker к write-аккаунту, произвольный SQL от LLM и запуск Qdrant backfill без отдельного подтверждения.
