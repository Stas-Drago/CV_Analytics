from datetime import UTC, datetime, timedelta
from uuid import uuid4

from surveillance.events.models import DetectedEvent
from surveillance.storage.postgres import Base, PostgresEventRepository


def test_persists_frame_crop_and_outbox(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(repository.engine)
    event = DetectedEvent(event_id=uuid4(), track_id="1", occurred_at=datetime.now(UTC),
                          object_type="person", confidence=0.9, bbox=[1, 2, 3, 4],
                          frame_jpeg=b"full-frame", object_crop_jpeg=b"crop", model_version="test",
                          deduplication_key="local-camera:1:person:1")

    event_id = repository.upsert_event(event)
    stored = repository.get_event(event_id)
    assert stored is not None
    assert stored.frame_data == b"full-frame"
    assert stored.object_crop == b"crop"


def test_duplicate_deduplication_key_is_idempotent(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(repository.engine)
    common = dict(track_id="1", occurred_at=datetime.now(UTC), object_type="person", confidence=0.9,
                  bbox=[1, 2, 3, 4], frame_jpeg=b"frame", object_crop_jpeg=b"crop", model_version="test",
                  deduplication_key="local-camera:1:person:1")
    first = repository.upsert_event(DetectedEvent(event_id=uuid4(), **common))
    second = repository.upsert_event(DetectedEvent(event_id=uuid4(), **common))
    assert second == first


def test_cursor_pagination_does_not_skip_events(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(repository.engine)
    now = datetime.now(UTC)
    expected_ids = []
    for index in range(5):
        event_id = uuid4()
        expected_ids.append(str(event_id))
        repository.upsert_event(DetectedEvent(
            event_id=event_id,
            track_id=str(index),
            occurred_at=now - timedelta(seconds=index),
            object_type="person",
            confidence=0.9,
            bbox=[1, 2, 3, 4],
            frame_jpeg=b"frame",
            object_crop_jpeg=b"crop",
            model_version="test",
            deduplication_key=f"local-camera:{index}:person:1",
        ))

    first, cursor = repository.list_events_page(2)
    second, cursor = repository.list_events_page(2, cursor)
    third, cursor = repository.list_events_page(2, cursor)

    actual_ids = [card["event"].event_id for card in first + second + third]
    assert actual_ids == expected_ids
    assert cursor is None
