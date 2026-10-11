from datetime import UTC, datetime
from uuid import uuid4
from surveillance.domain import EventCreate


def test_event_schema_requires_known_camera_and_valid_confidence() -> None:
    event = EventCreate(event_id=uuid4(), camera_id="camera-1", track_id="42", occurred_at=datetime.now(UTC),
                        object_type="person", confidence=0.9, bbox=[1, 2, 3, 4], model_version="yolo11n")
    assert event.occurred_at.tzinfo is not None
