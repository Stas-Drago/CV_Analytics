"""Explicit camera worker entrypoint; never imported by the API process."""
from datetime import UTC, datetime
from uuid import uuid4
from surveillance.config import settings
from surveillance.domain import EventCreate


def build_event(camera_id: str, track_id: int, label: str, confidence: float, bbox: list[int], uri: str) -> EventCreate:
    return EventCreate(
        event_id=uuid4(), camera_id=camera_id, track_id=str(track_id), occurred_at=datetime.now(UTC),
        object_type=label, confidence=confidence, bbox=bbox, media_uri=uri, model_version="yolo11n",
    )


def run() -> None:
    """Start only from a dedicated process after camera/YOLO configuration is validated."""
    if not settings().cameras:
        raise RuntimeError("No camera URLs configured")
    raise NotImplementedError("Camera adapter must publish EventCreate through the internal API/queue")
