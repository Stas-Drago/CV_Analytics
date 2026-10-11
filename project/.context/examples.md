# Примеры правильного кода

Примеры показывают целевой стиль; это не готовые для копирования без адаптации фрагменты.

## 1. Валидируемый контракт чата

```python
from pydantic import BaseModel, Field

class AssistantQuestion(BaseModel):
    request: str = Field(min_length=1, max_length=1_000)

@app.post("/makejob")
def make_job() -> tuple[dict, int] | dict:
    payload = AssistantQuestion.model_validate(request.get_json(silent=False))
    answer = assistant_service.answer(payload.request)
    return {"answer": answer.text, "citations": answer.citations}
```

```js
const response = await fetch('/makejob', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({request: question}),
});
if (!response.ok) throw new Error('Не удалось получить ответ');
const {answer} = await response.json();
appendMessage('Модель', answer, 'bot');
```

## 2. Единое время и параметризованный фильтр

```python
from datetime import UTC, datetime

def parse_rfc3339(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone is required')
    return parsed.astimezone(UTC)

def search_events(conn, *, camera_id: str | None, start: datetime | None):
    sql = 'SELECT event_id, occurred_at, camera_id, description FROM events WHERE 1=1'
    params: list[object] = []
    if camera_id:
        sql += ' AND camera_id = ?'
        params.append(camera_id)
    if start:
        sql += ' AND occurred_at >= ?'
        params.append(start.isoformat())
    sql += ' ORDER BY occurred_at DESC LIMIT ?'
    params.append(100)
    return conn.execute(sql, params).fetchall()
```

## 3. Идемпотентное событие и payload для retrieval

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Event:
    event_id: str
    camera_id: str
    track_id: str
    occurred_at: datetime  # aware UTC
    object_type: str
    description: str
    source_uri: str
    model_version: str

def qdrant_payload(event: Event) -> dict[str, str]:
    return {
        'event_id': event.event_id,
        'camera_id': event.camera_id,
        'occurred_at': event.occurred_at.isoformat(),
        'object_type': event.object_type,
        'text': event.description,
        'source_uri': event.source_uri,
        'model_version': event.model_version,
    }
```

## 4. Безопасная постановка vision-задачи

```python
from queue import Full, Queue

vision_queue: Queue[Event] = Queue(maxsize=500)

def publish_event(event: Event) -> bool:
    try:
        vision_queue.put_nowait(event)
    except Full:
        metrics.increment('vision_queue_dropped_total')
        return False
    metrics.increment('vision_queue_enqueued_total')
    return True
```

Capture worker только создаёт событие и сохраняет кадр; vision worker читает очередь, использует timeout/retry и в `finally` очищает временный ресурс. Это не допускает остановки камеры из-за медленной LLM.

## 5. Безопасный вывод текста в DOM

```js
function appendMessage(author, message, className) {
  const element = document.createElement('div');
  element.className = `message ${className}`;
  const title = document.createElement('strong');
  title.textContent = `${author}: `;
  element.append(title, document.createTextNode(message));
  document.querySelector('#chatLog').append(element);
}
```

## 6. Evidence-grounded ответ

```python
def build_context(events: list[Event]) -> str:
    return '\n'.join(
        f'[{e.event_id}] {e.occurred_at.isoformat()} {e.camera_id}: {e.description}'
        for e in events[:8]
    )

SYSTEM_RULE = (
    'Отвечай только по контексту. Для каждого утверждения укажи event_id. '
    'Если доказательств нет, ответь: «Недостаточно данных для подтверждения». '
    'Не идентифицируй людей и не квалифицируй действия как нарушение.'
)
```
