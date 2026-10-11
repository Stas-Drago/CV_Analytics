from dataclasses import dataclass


@dataclass(frozen=True)
class IndexEvent:
    event_id: str


class Outbox:
    """Contract for retrying PostgreSQL-to-Qdrant indexing after a committed event."""

    def enqueue(self, event_id: str) -> None:
        raise NotImplementedError
