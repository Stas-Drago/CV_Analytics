import logging
from contextlib import contextmanager
from datetime import UTC

import redis

from surveillance.analysis.risk import DangerMLPRiskScorer
from surveillance.analysis.vision import VisionResult
from surveillance.storage.postgres import PostgresEventRepository

logger = logging.getLogger(__name__)


class InferenceGate:
    """A Redis mutex serialising heavy host inference on a 16 GB Mac."""

    def __init__(self, redis_url: str, key: str) -> None:
        self.client = redis.from_url(redis_url)
        self.key = key

    @contextmanager
    def hold(self):
        lock = self.client.lock(self.key, timeout=120, blocking_timeout=0)
        if not lock.acquire(blocking=False):
            yield False
            return
        try:
            yield True
        finally:
            try:
                lock.release()
            except redis.exceptions.LockError:
                logger.warning("analysis lock expired before release")


class VisionWorker:
    def __init__(self, repository: PostgresEventRepository, client: object,
                 gate: InferenceGate, max_attempts: int) -> None:
        self.repository, self.client, self.gate, self.max_attempts = repository, client, gate, max_attempts

    def run_once(self) -> bool:
        job = self.repository.claim_job("vision")
        if not job:
            return False
        with self.gate.hold() as acquired:
            if not acquired:
                self.repository.defer_job(job.id)
                return False
            try:
                event = self.repository.get_event(job.event_id)
                if not event:
                    raise LookupError(f"event {job.event_id} not found")
                result: VisionResult = self.client.describe(event.frame_data, event.object_type, event.confidence, event.bbox)
                self.repository.save_vision_analysis(job.event_id, result.description, result.model_name,
                                                     result.model_version, result.prompt_version)
                self.repository.complete_job(job.id)
                return True
            except Exception as error:
                logger.exception("vision job failed: %s", job.id)
                self.repository.fail_job(job.id, str(error), self.max_attempts)
                return False


class RiskWorker:
    def __init__(self, repository: PostgresEventRepository, scorer: DangerMLPRiskScorer,
                 gate: InferenceGate, max_attempts: int) -> None:
        self.repository, self.scorer, self.gate, self.max_attempts = repository, scorer, gate, max_attempts

    def run_once(self) -> bool:
        job = self.repository.claim_job("risk")
        if not job:
            return False
        with self.gate.hold() as acquired:
            if not acquired:
                self.repository.defer_job(job.id)
                return False
            try:
                vision = self.repository.latest_vision_analysis(job.event_id)
                if not vision:
                    raise LookupError(f"vision analysis for {job.event_id} not found")
                result = self.scorer.score(vision.description)
                self.repository.save_risk_assessment(job.event_id, vision.id, result.level, result.probabilities,
                                                     result.model_version, result.model_checksum,
                                                     result.mapping_version, result.threshold_policy_version)
                self.repository.complete_job(job.id)
                return True
            except Exception as error:
                logger.exception("risk job failed: %s", job.id)
                self.repository.fail_job(job.id, str(error), self.max_attempts)
                return False


def qdrant_payload(event, vision, risk, embedding_model: str, revision: int) -> dict:
    """Payload is metadata only; PostgreSQL retains all media bytes."""
    risk_payload = None
    if risk:
        risk_payload = {
            "level": risk.predicted_level,
            "probabilities": risk.probabilities,
            "mode": risk.mode,
            "model_version": risk.model_version,
            "model_checksum": risk.model_checksum,
            "mapping_version": risk.mapping_version,
            "threshold_policy_version": risk.threshold_policy_version,
        }
    return {
        "event_id": event.event_id,
        "camera_id": event.camera_id,
        "occurred_at": event.occurred_at.astimezone(UTC).isoformat(),
        "object_type": event.object_type,
        "text": event.description,
        "risk": risk_payload,
        "models": {
            "yolo": event.model_version,
            "vision": {
                "name": vision.model_name,
                "version": vision.model_version,
                "prompt_version": vision.prompt_version,
            },
            "danger_mlp": None if not risk else risk.model_version,
        },
        "embedding_model": embedding_model,
        "index_revision": revision,
    }


class QdrantWorker:
    """Indexes PostgreSQL-owned event metadata with a stable Qdrant point ID."""

    def __init__(self, repository: PostgresEventRepository, index: object, embedder: object,
                 gate: InferenceGate, max_attempts: int, embedding_model: str,
                 processing_timeout_seconds: int) -> None:
        self.repository = repository
        self.index = index
        self.embedder = embedder
        self.gate = gate
        self.max_attempts = max_attempts
        self.embedding_model = embedding_model
        self.processing_timeout_seconds = processing_timeout_seconds

    def run_once(self) -> bool:
        job = self.repository.claim_job("qdrant", self.processing_timeout_seconds)
        if not job:
            return False
        claimed_revision = job.revision
        try:
            data = self.repository.qdrant_index_data(job.event_id)
            if not data:
                raise LookupError(f"indexable event {job.event_id} not found")
            event, vision, risk = data
            self.index.ensure_collection()
            with self.gate.hold() as acquired:
                if not acquired:
                    self.repository.defer_job(job.id)
                    return False
                vector = self.embedder.encode(event.description)
            self.index.upsert(
                event.event_id,
                vector,
                qdrant_payload(event, vision, risk, self.embedding_model, claimed_revision),
            )
            self.repository.complete_qdrant_job(job.id, claimed_revision)
            return True
        except Exception as error:
            logger.exception("Qdrant job failed: %s", job.id)
            self.repository.fail_qdrant_job(job.id, claimed_revision, str(error), self.max_attempts)
            return False
