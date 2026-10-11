from contextlib import asynccontextmanager
from datetime import UTC
from uuid import UUID
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from surveillance.config import Settings, settings
from surveillance.db import Repository
from surveillance.domain import AlertDecision, EventCreate, Question
from surveillance.queue import TaskQueue


def event_payload(event) -> dict:
    return {
        "event_id": event.event_id, "camera_id": event.camera_id, "track_id": event.track_id,
        "occurred_at": event.occurred_at.astimezone(UTC).isoformat(), "object_type": event.object_type,
        "confidence": event.confidence, "description": event.description, "media_uri": event.media_uri,
        "risk_level": event.risk_level, "risk_probability": event.risk_probability,
        "alert_status": event.alert_status,
    }


def create_app(app_settings: Settings | None = None) -> FastAPI:
    config = app_settings or settings()
    repository = Repository(config.database_url)
    queue = TaskQueue(config.redis_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.create_schema()
        yield

    app = FastAPI(title="Surveillance API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/events", status_code=202)
    def enqueue_event(item: EventCreate) -> dict[str, str]:
        event = repository.create_event(item)
        queue.publish(event.event_id)
        return {"event_id": event.event_id, "status": "queued"}

    @app.get("/events")
    def events(camera_id: str | None = None, limit: int = Query(default=50, ge=1, le=100)) -> list[dict]:
        return [event_payload(event) for event in repository.list_events(camera_id=camera_id, limit=limit)]

    @app.get("/alerts")
    def alerts() -> list[dict]:
        return [e for e in (event_payload(v) for v in repository.list_events(limit=100)) if e["risk_level"] == "high"]

    @app.post("/alerts/{event_id}")
    def decide_alert(event_id: UUID, decision: AlertDecision) -> dict:
        event = repository.set_alert(event_id, decision.status, decision.note)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return event_payload(event)

    @app.post("/makejob")
    def ask(question: Question) -> dict:
        # RAG worker will replace this explicit safe response after Qdrant integration.
        return {"answer": "Поиск подготовлен. Вопрос принят: " + question.request, "citations": []}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return "<h1>Surveillance dashboard</h1><p>Use the authenticated internal UI deployment.</p>"

    return app
