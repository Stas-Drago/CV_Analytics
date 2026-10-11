from surveillance.events.models import DetectedEvent
from surveillance.storage.postgres import PostgresEventRepository


class EventService:
    """PostgreSQL is the source of truth; Qdrant indexing is performed after persistence."""

    def __init__(self, repository: PostgresEventRepository) -> None:
        self.repository = repository

    def record(self, event: DetectedEvent) -> str:
        return self.repository.upsert_event(event)
