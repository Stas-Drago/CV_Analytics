from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from math import sqrt
from uuid import uuid4

from surveillance.events.models import DetectedEvent
from surveillance.storage.postgres import Base, OutboxRow, PostgresEventRepository
from surveillance.workers.pipeline import QdrantWorker


class OpenGate:
    @contextmanager
    def hold(self):
        yield True


class FakeEmbedder:
    def encode(self, text):
        assert text
        return [1 / sqrt(768)] * 768


class FakeIndex:
    def __init__(self, error=None):
        self.error, self.points, self.upserts = error, {}, 0

    def ensure_collection(self):
        if self.error:
            raise self.error

    def upsert(self, event_id, vector, payload):
        self.upserts += 1
        self.points[event_id] = {"vector": vector, "payload": payload}


def event() -> DetectedEvent:
    return DetectedEvent(event_id=uuid4(), track_id="9", occurred_at=datetime.now(UTC), object_type="car",
                         confidence=0.9, bbox=[1, 2, 3, 4], frame_jpeg=b"frame", object_crop_jpeg=b"crop",
                         model_version="yolo-v1", deduplication_key=f"camera:9:car:{uuid4()}")


def repository(tmp_path) -> PostgresEventRepository:
    result = PostgresEventRepository(f"sqlite:///{tmp_path / 'qdrant.db'}")
    Base.metadata.create_all(result.engine)
    return result


def worker(repository, index):
    return QdrantWorker(repository, index, FakeEmbedder(), OpenGate(), 3, "sentence-transformers/LaBSE", 300)


def test_vision_description_is_indexed_once_and_payload_has_no_media(tmp_path) -> None:
    store = repository(tmp_path)
    event_id = store.upsert_event(event())
    store.save_vision_analysis(event_id, "В кадре виден автомобиль.", "qwen", "qwen-v1", "prompt-v1")
    index = FakeIndex()

    assert worker(store, index).run_once() is True
    assert len(index.points) == 1
    point = index.points[event_id]
    assert point["payload"]["event_id"] == event_id
    assert point["payload"]["risk"] is None
    assert point["payload"]["models"]["vision"]["version"] == "qwen-v1"
    assert "frame_data" not in point["payload"] and "object_crop" not in point["payload"]

    store.schedule_qdrant_backfill()
    assert worker(store, index).run_once() is True
    assert len(index.points) == 1 and index.upserts == 2


def test_risk_update_requeues_new_revision_after_an_inflight_claim(tmp_path) -> None:
    store = repository(tmp_path)
    event_id = store.upsert_event(event())
    vision = store.save_vision_analysis(event_id, "В кадре виден автомобиль.", "qwen", "qwen-v1", "prompt-v1")
    job = store.claim_job("qdrant")
    assert job is not None and job.revision == 1

    store.save_risk_assessment(event_id, vision.id, "high", {"low": 0.1, "medium": 0.1, "high": 0.8},
                               "danger-v1", "checksum", "mapping-v1", "policy-v1")
    assert store.complete_qdrant_job(job.id, job.revision) is False
    next_job = store.claim_job("qdrant")
    assert next_job is not None and next_job.revision == 2


def test_qdrant_retries_then_dead_and_recovers_when_requeued(tmp_path) -> None:
    store = repository(tmp_path)
    event_id = store.upsert_event(event())
    store.save_vision_analysis(event_id, "В кадре виден автомобиль.", "qwen", "qwen-v1", "prompt-v1")
    failing = worker(store, FakeIndex(RuntimeError("Qdrant unavailable")))

    for expected_attempt in (1, 2, 3):
        assert failing.run_once() is False
        with store.sessions.begin() as session:
            job = session.query(OutboxRow).filter_by(event_id=event_id, kind="qdrant").one()
            assert job.attempts == expected_attempt
            if expected_attempt < 3:
                job.available_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                assert job.status == "dead"

    assert store.requeue_dead_qdrant_jobs() == 1
    recovered = FakeIndex()
    assert worker(store, recovered).run_once() is True
    assert event_id in recovered.points


def test_stale_processing_qdrant_job_is_claimed_again(tmp_path) -> None:
    store = repository(tmp_path)
    event_id = store.upsert_event(event())
    store.save_vision_analysis(event_id, "В кадре виден автомобиль.", "qwen", "qwen-v1", "prompt-v1")
    first = store.claim_job("qdrant")
    assert first is not None
    with store.sessions.begin() as session:
        row = session.get(OutboxRow, first.id)
        row.locked_at = datetime.now(UTC) - timedelta(seconds=301)
    recovered = store.claim_job("qdrant", processing_timeout_seconds=300)
    assert recovered is not None and recovered.id == first.id
