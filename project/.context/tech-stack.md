# Технологический стек и зависимости

## Фактически обнаруженный стек

| Слой | Технология | Назначение | Зафиксированная версия |
|---|---|---|---|
| Язык | Python | backend и workers | Не зафиксирована; pycache указывает на CPython 3.9 |
| Web | Flask + Waitress | HTTP API, HTML, production-like WSGI serving | Не зафиксирована |
| CV | OpenCV, Ultralytics YOLO | MJPEG capture, bbox, detection/tracking | Не зафиксирована; веса `yolo11n.pt` |
| Tracking | Ultralytics track + custom `UniqueObjectTracker` | Отслеживание объектов | Конфиг `bytetrack.yaml` не соответствует актуальному стандартному формату |
| Vision LLM | Ollama, `gemma3:12b-it-qat` | Описание crop объекта | Версия Ollama не зафиксирована |
| Embeddings | sentence-transformers, `sentence-transformers/LaBSE` | Векторизация журналов и запросов | Не зафиксирована |
| Reranking | CrossEncoder, `cross-encoder/ms-marco-MiniLM-L-2-v2` | Переранжирование кандидатов | Не зафиксирована |
| Vector DB | Qdrant client + локальный Qdrant | Semantic retrieval | Не зафиксирована; `qdrant_data/` ~131 MB |
| Реляционное хранилище | SQLite | `logs` | Встроенная версия Python; schema inline |
| Text LLM | OpenAI-compatible client → Bothub, `mistral-large` | Генерация ответа охраннику | Клиент/модель не зафиксированы; key должен быть во внешнем secret |
| Service registry | requests | POST регистрации | Не зафиксирована |
| UI | Jinja2 template, vanilla JS/CSS | Видеостена, фильтры, чат | Не зафиксирована |

## Что отсутствует

В проекте нет `pyproject.toml`, `requirements.txt`, lock-файла, Dockerfile, Compose, `.env.example`, README, CI и тестов. Нельзя считать список импортов воспроизводимой средой: версии, CUDA/CPU-сборки, доступность веса, Ollama model и Qdrant server должны быть закреплены отдельно.

## Обязательная минимальная поставка

Создать `pyproject.toml` (предпочтительно) или `requirements.txt` с точными версиями, затем lock-файл. Разделить зависимости:

```text
runtime: flask, waitress, opencv-python(-headless), ultralytics, ollama,
         pillow, sentence-transformers, qdrant-client, openai, requests
dev:     pytest, pytest-cov, ruff, mypy, pre-commit, pip-audit
```

Версии выбирать только после smoke-теста полного набора: Python, ОС, CPU/GPU, Ultralytics tracker YAML, Qdrant API и доступные Ollama модели. Зафиксировать checksum/источник `yolo11n.pt` и версии embedding/reranker моделей, поскольку они являются частью совместимости векторной коллекции.

## Конфигурация: только окружение

Следующие значения запрещено хранить в Python/HTML/Git:

```text
CAMERA_1_URL ... CAMERA_4_URL
QDRANT_URL / QDRANT_API_KEY
OLLAMA_HOST / OLLAMA_MODEL
LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
REGISTRY_URL / SERVICE_UUID / PUBLIC_ENDPOINT
DATABASE_URL
```

В репозиторий допускается только `.env.example` с пустыми/примерными значениями. Валидировать конфигурацию на старте и завершать запуск с понятной ошибкой, не печатая секрет.

## Совместимость данных и моделей

- Изменение LaBSE/embedding model или размерности вектора требует новой Qdrant collection/reindex, а не записи в старую.
- Изменение OCR/vision prompt, YOLO weights или tracker config должно фиксироваться в `model_run`/event metadata.
- Сырой каталог Qdrant — stateful runtime data: запускать в volume, backup штатными средствами Qdrant, исключить из Git.

## Этап 5: поиск и аналитика

- FastAPI `POST /api/query` передаёт запрос в Redis Streams; модели в API-контейнер не загружаются.
- Host-only `query-worker`: Python 3.12, `redis==5.2.1`, `httpx==0.27.2`, `sentence-transformers/LaBSE`, `qdrant-client==1.12.1`, SQLAlchemy и `psycopg`.
- Intent и evidence-grounded summary исполняет локальный Ollama Qwen; LLM возвращает JSON по Pydantic schema и не исполняет SQL.
- Аналитика выполняется отдельной PostgreSQL-ролью `surveillance_reader` только через `analytics_events` view. Пароль задаётся исключительно в `POSTGRES_READER_PASSWORD` / `ANALYTICS_DATABASE_URL` на хосте.
- Временные границы: `Europe/Moscow` на входе, UTC в PostgreSQL/Qdrant. Reader transaction имеет `READ ONLY` и `statement_timeout=3000ms`.
