# CV Analytics

Локальная система видеоаналитики для одной USB-камеры. Проект обнаруживает объекты в видеопотоке, сохраняет события и JPEG-кадры, создаёт русскоязычное описание события, оценивает риск и предоставляет оператору поиск естественным языком.

## Основные возможности

- YOLO26n и ByteTrack для обнаружения и сопровождения объектов.
- Защита от повторных событий одного объекта: стабильный `track_id`, cooldown и уникальный ключ PostgreSQL.
- Локальный vision-анализ через Qwen/MLX или Ollama в зависимости от конфигурации.
- DangerMLP на LaBSE-embedding с классами `low`, `medium`, `high`.
- Дублирование текстовых данных: PostgreSQL — источник истины, Qdrant — семантический индекс.
- Безопасный Query Router: общие вопросы направляются в Qdrant, количественные запросы — в разрешённые параметризованные SQL-операции.
- Web-dashboard с RBAC, preview, карточками событий, shadow/high-очередью и ручными решениями оператора.

## Архитектура

```text
USB-камера
    ↓
camera-ingest → YOLO26n + ByteTrack
    ↓
PostgreSQL events/outbox ← Redis
    ↓
vision-worker → Qwen2.5-VL → risk-worker → DangerMLP
    ↓                                  ↓
Qdrant semantic index             operator_tasks
    ↓                                  ↓
FastAPI API ← Nginx ← JavaScript dashboard
```

`camera-ingest` запускается на хосте с физической камерой. PostgreSQL, Redis, Qdrant, FastAPI и web запускаются через Docker Compose. Видеопоток не записывается на диск.

## Быстрый запуск

Требования: macOS с Python 3.12, Docker Desktop, локальная USB-камера и, при необходимости, Ollama или MLX.

```bash
cp .env.example .env
cp .env.host.example .env.host
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[vision,dev]"
docker compose up -d postgres redis qdrant migrate api web
```

После запуска:

- API: http://127.0.0.1:8000
- Web-интерфейс: http://127.0.0.1:8080
- Qdrant: http://127.0.0.1:6333

Камеру запускают отдельно на macOS:

```bash
source .venv/bin/activate
set -a; source .env.host; set +a
bash scripts/run_camera_ingest.sh
```

Workers запускаются вручную на хосте, когда установлены соответствующие модели:

```bash
bash scripts/run_analysis_worker.sh
bash scripts/run_risk_worker.sh
bash scripts/run_query_worker.sh
```

## Миграции и тесты

Миграции применяются контейнером `migrate` и используют таблицу `schema_migrations`. Повторный запуск безопасен.

```bash
python scripts/apply_migrations.py
pytest
ruff check src tests scripts
```

## DangerMLP

Модель получает не изображение, а русское описание vision-модели. LaBSE строит embedding размерности 768, после чего обучаемая голова выполняет преобразование `768 → 256 → 64 → 3` с ReLU, dropout и softmax.

Классы:

- `low` — обычная активность;
- `medium` — события, требующие внимания;
- `high` — только «требует проверки».

`high` не является подтверждённым инцидентом и не запускает автоматических внешних действий. До отдельного утверждения выпуск работает в shadow mode. Веса и датасеты не хранятся в Git; в репозитории находятся только manifests, model card и код pipeline.

## Безопасность

- Секреты задаются через `.env` и `.env.host`, а не хранятся в репозитории.
- Роли: `viewer`, `operator`, `supervisor`.
- Кадры и live-preview доступны только `operator` и `supervisor`.
- SQL для пользовательских вопросов не генерируется и не исполняется напрямую: используются только allowlist-операции и read-only reader role.
- Решения `confirm`, `reject` и shadow-разметка сохраняются в append-only audit trail.
- Для публичного репозитория исключены кадры, видео, runtime-данные Qdrant, веса моделей, локальные базы, логи и пароли.

## Документация

- `.context/architecture.md` — архитектура и ограничения.
- `.context/новая архитектура.md` — согласованная целевая структура.
- `.context/remaining-work.md` — текущий список работ.
- `docs/stage1-runbook.md` … `docs/stage7-runbook.md` — runbook по этапам.
- `docs/synthetic-risk-training.md` — генерация синтетического набора и обучение.
- `models/model_card.md` — описание DangerMLP и ограничений метрик.

## Ограничения

Проект предназначен для локального исследовательского и операторского контура. DangerMLP, Qwen и YOLO помогают находить и ранжировать наблюдения, но не распознают личности, не делают выводы о намерениях и не принимают автономных охранных решений.

