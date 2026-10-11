from datetime import UTC, datetime
from uuid import uuid4

from surveillance.events.models import DetectedEvent
from surveillance.storage.postgres import Base, OperatorDecisionAuditRow, PostgresEventRepository


def event() -> DetectedEvent:
    return DetectedEvent(event_id=uuid4(), track_id="9", occurred_at=datetime.now(UTC), object_type="car",
                         confidence=0.9, bbox=[1, 2, 3, 4], frame_jpeg=b"frame", object_crop_jpeg=b"crop",
                         model_version="yolo", deduplication_key="camera:9:car:1")


def test_pipeline_creates_shadow_task_only_for_high(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'analysis.db'}")
    Base.metadata.create_all(repository.engine)
    event_id = repository.upsert_event(event())
    vision_job = repository.claim_job("vision")
    assert vision_job is not None
    vision = repository.save_vision_analysis(event_id, "В кадре виден автомобиль.", "qwen", "qwen-v1", "p1")
    repository.complete_job(vision_job.id)
    risk_job = repository.claim_job("risk")
    assert risk_job is not None
    repository.save_risk_assessment(event_id, vision.id, "high", {"low": 0.1, "medium": 0.1, "high": 0.8},
                                    "danger-v1", "sha", "mapping-v1", "shadow-v1")
    repository.complete_job(risk_job.id)
    card = repository.list_event_cards(10)[0]
    assert card["assessment"].probabilities["high"] == 0.8
    assert card["task"].mode == "shadow"
    assert card["task"].status == "pending"


def test_pipeline_does_not_create_task_for_non_high(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'analysis.db'}")
    Base.metadata.create_all(repository.engine)
    event_id = repository.upsert_event(event())
    vision = repository.save_vision_analysis(event_id, "В кадре виден автомобиль.", "qwen", "qwen-v1", "p1")
    repository.save_risk_assessment(event_id, vision.id, "low", {"low": 0.8, "medium": 0.1, "high": 0.1},
                                    "danger-v1", "sha", "mapping-v1", "shadow-v1")
    card = repository.list_event_cards(10)[0]
    assert card["task"] is None


def test_risk_backfill_is_idempotent_per_model_and_latest_vision(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'backfill.db'}")
    Base.metadata.create_all(repository.engine)
    event_id = repository.upsert_event(event())
    vision = repository.save_vision_analysis(event_id, "Автомобиль у здания.", "qwen", "qwen-v1", "p1")
    assert repository.schedule_risk_backfill("danger-v1") == 1
    job = repository.claim_job("risk")
    assert job is not None
    repository.save_risk_assessment(event_id, vision.id, "low", {"low": .8, "medium": .1, "high": .1},
                                    "danger-v1", "sha", "mapping-v1", "shadow-v1")
    repository.complete_job(job.id)
    assert repository.schedule_risk_backfill("danger-v1") == 0
    assert repository.schedule_risk_backfill("danger-v2") == 1


def test_deferring_busy_job_does_not_consume_retry(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'analysis.db'}")
    Base.metadata.create_all(repository.engine)
    repository.upsert_event(event())
    job = repository.claim_job("vision")
    assert job is not None and job.attempts == 1
    repository.defer_job(job.id)
    deferred = repository.claim_job("vision")
    assert deferred is None  # one-second defer prevents hot-looping while the lock is held


def test_operator_decision_is_atomic_and_audited(tmp_path) -> None:
    repository = PostgresEventRepository(f"sqlite:///{tmp_path / 'decision.db'}")
    Base.metadata.create_all(repository.engine)
    event_id = repository.upsert_event(event())
    vision = repository.save_vision_analysis(event_id, "Автомобиль.", "qwen", "qwen-v1", "p1")
    repository.save_risk_assessment(event_id, vision.id, "high", {"low": .1, "medium": .1, "high": .8},
                                    "danger-v1", "sha", "mapping-v1", "shadow-v1")
    task = repository.list_event_cards(1)[0]["task"]
    decided = repository.decide_task(task.id, "confirm", None, "Проверено", 7, "operator")
    assert decided and decided.status == "confirmed"
    assert repository.decide_task(task.id, "reject", None, "Повтор", 7, "operator") is None
    with repository.sessions() as session:
        audit = session.query(OperatorDecisionAuditRow).one()
    assert (audit.action, audit.actor_username, audit.note) == ("confirm", "operator", "Проверено")
