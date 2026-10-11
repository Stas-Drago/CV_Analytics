from datetime import UTC, datetime, timedelta

from sqlalchemy import (DateTime, Float, JSON, LargeBinary, String, Text, UniqueConstraint, Uuid,
                        create_engine, func, or_, select)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from surveillance.events.models import DetectedEvent


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("deduplication_key", name="events_deduplication_key_key"),)
    # The database migration stores identifiers as PostgreSQL UUID, not VARCHAR.
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(100), index=True)
    track_id: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    object_type: Mapped[str] = mapped_column(String(100), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    bbox: Mapped[list[int]] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), index=True, nullable=True)
    risk_probability: Mapped[dict] = mapped_column(JSON, nullable=True)
    risk_rationale: Mapped[str] = mapped_column(Text, default="")
    media_uri: Mapped[str] = mapped_column(Text, default="")
    frame_data: Mapped[bytes] = mapped_column(LargeBinary)
    object_crop: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    frame_media_type: Mapped[str] = mapped_column(String(50), default="image/jpeg")
    model_version: Mapped[str] = mapped_column(String(100))
    alert_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    operator_note: Mapped[str] = mapped_column(Text, default="")
    deduplication_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)


class OutboxRow(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (UniqueConstraint("event_id", "kind", name="event_outbox_event_kind_key"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="vision")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)


class VisionAnalysisRow(Base):
    __tablename__ = "vision_analyses"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    description: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="completed")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class RiskAssessmentRow(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (UniqueConstraint("event_id", "vision_analysis_id", "model_version", name="risk_assessment_release_key"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    vision_analysis_id: Mapped[int] = mapped_column(index=True)
    predicted_level: Mapped[str] = mapped_column(String(16))
    probabilities: Mapped[dict[str, float]] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(200))
    model_checksum: Mapped[str] = mapped_column(String(128))
    mapping_version: Mapped[str] = mapped_column(String(100))
    threshold_policy_version: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(16), default="shadow")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class OperatorTaskRow(Base):
    __tablename__ = "operator_tasks"
    __table_args__ = (UniqueConstraint("risk_assessment_id", "mode", name="operator_task_assessment_mode_key"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    risk_assessment_id: Mapped[int] = mapped_column(index=True)
    mode: Mapped[str] = mapped_column(String(16), default="shadow")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    operator_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    operator_note: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class QueryAuditLogRow(Base):
    __tablename__ = "query_audit_log"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_hash: Mapped[str] = mapped_column(String(64), index=True)
    route: Mapped[str] = mapped_column(String(16))
    operation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(default=0)
    result_count: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), index=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperatorDecisionAuditRow(Base):
    __tablename__ = "operator_decision_audit"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(index=True)
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    risk_assessment_id: Mapped[int] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor_user_id: Mapped[int] = mapped_column(index=True)
    actor_username: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text, default="")
    previous_status: Mapped[str] = mapped_column(String(16))
    new_status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ModelReleaseRow(Base):
    __tablename__ = "model_releases"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(200), unique=True)
    checksum: Mapped[str] = mapped_column(String(128), unique=True)
    model_card_hash: Mapped[str] = mapped_column(String(128))
    mapping_version: Mapped[str] = mapped_column(String(100))
    threshold_policy_version: Mapped[str] = mapped_column(String(100))
    dataset_version: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    registered_by: Mapped[str] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ModelEvaluationRow(Base):
    __tablename__ = "model_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    release_id: Mapped[int] = mapped_column(index=True)
    sample_count: Mapped[int] = mapped_column()
    macro_f1: Mapped[float] = mapped_column(Float)
    high_recall: Mapped[float] = mapped_column(Float)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    language: Mapped[str] = mapped_column(String(16), default="ru")
    source: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PostgresEventRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def upsert_event(self, event: DetectedEvent) -> str:
        event_id = str(event.event_id)
        try:
            with self.sessions.begin() as session:
                duplicate = session.scalar(
                    select(EventRow.event_id).where(EventRow.deduplication_key == event.deduplication_key)
                )
                if duplicate:
                    return duplicate
                session.add(EventRow(event_id=event_id, camera_id=event.camera_id, track_id=event.track_id,
                            occurred_at=event.occurred_at, object_type=event.object_type,
                            confidence=event.confidence, bbox=event.bbox, frame_data=event.frame_jpeg,
                            object_crop=event.object_crop_jpeg, model_version=event.model_version,
                            media_uri="", risk_rationale="", deduplication_key=event.deduplication_key))
                session.add(OutboxRow(event_id=event_id, kind="vision"))
        except IntegrityError:
            with self.sessions() as session:
                duplicate = session.scalar(
                    select(EventRow.event_id).where(EventRow.deduplication_key == event.deduplication_key)
                )
                if duplicate:
                    return duplicate
            raise
        return event_id

    def list_events(self, limit: int = 50) -> list[EventRow]:
        with self.sessions() as session:
            statement = select(EventRow).order_by(EventRow.occurred_at.desc()).limit(limit)
            return list(session.scalars(statement))

    def get_event(self, event_id: str) -> EventRow | None:
        with self.sessions() as session:
            return session.get(EventRow, event_id)

    def claim_job(self, kind: str, processing_timeout_seconds: int = 300) -> OutboxRow | None:
        """Claim one durable job. PostgreSQL adds SKIP LOCKED; SQLite remains test-friendly."""
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            stale_before = now - timedelta(seconds=processing_timeout_seconds)
            stale_jobs = session.scalars(select(OutboxRow).where(
                OutboxRow.kind == kind,
                OutboxRow.status == "processing",
                or_(OutboxRow.locked_at.is_(None), OutboxRow.locked_at < stale_before),
            ))
            for stale_job in stale_jobs:
                stale_job.status, stale_job.locked_at = "pending", None
                stale_job.available_at = now
                stale_job.last_error = "worker claim expired"
            statement = (select(OutboxRow).where(OutboxRow.kind == kind,
                         OutboxRow.status == "pending", OutboxRow.available_at <= now)
                         .order_by(OutboxRow.available_at.desc(), OutboxRow.id.desc()).limit(1))
            if session.bind and session.bind.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            job = session.scalar(statement)
            if not job:
                return None
            job.status, job.locked_at, job.attempts = "processing", now, job.attempts + 1
            return job

    def complete_job(self, job_id: int) -> None:
        with self.sessions.begin() as session:
            job = session.get(OutboxRow, job_id)
            if job:
                job.status, job.locked_at, job.last_error = "completed", None, ""

    def fail_job(self, job_id: int, error: str, max_attempts: int) -> None:
        with self.sessions.begin() as session:
            job = session.get(OutboxRow, job_id)
            if not job:
                return
            job.last_error, job.locked_at = error[:4000], None
            if job.attempts >= max_attempts:
                job.status = "dead"
            else:
                job.status = "pending"
                job.available_at = datetime.now(UTC) + timedelta(seconds=2 ** job.attempts)

    def defer_job(self, job_id: int) -> None:
        """Return a job after a busy global inference lock without consuming a retry."""
        with self.sessions.begin() as session:
            job = session.get(OutboxRow, job_id)
            if job:
                job.status, job.locked_at = "pending", None
                job.attempts = max(0, job.attempts - 1)
                job.available_at = datetime.now(UTC) + timedelta(seconds=1)

    def save_vision_analysis(self, event_id: str, description: str, model_name: str,
                             model_version: str, prompt_version: str) -> VisionAnalysisRow:
        with self.sessions.begin() as session:
            row = VisionAnalysisRow(event_id=event_id, description=description, model_name=model_name,
                                    model_version=model_version, prompt_version=prompt_version)
            session.add(row)
            event = session.get(EventRow, event_id)
            if event:
                event.description = description
            session.flush()
            existing = session.scalar(select(OutboxRow).where(OutboxRow.event_id == event_id,
                                                               OutboxRow.kind == "risk"))
            if not existing:
                session.add(OutboxRow(event_id=event_id, kind="risk"))
            self._schedule_qdrant_index(session, event_id)
            return row

    def latest_vision_analysis(self, event_id: str) -> VisionAnalysisRow | None:
        with self.sessions() as session:
            return session.scalar(select(VisionAnalysisRow).where(VisionAnalysisRow.event_id == event_id)
                                  .order_by(VisionAnalysisRow.id.desc()))

    def save_risk_assessment(self, event_id: str, vision_analysis_id: int, predicted_level: str,
                             probabilities: dict[str, float], model_version: str, model_checksum: str,
                             mapping_version: str, threshold_policy_version: str) -> RiskAssessmentRow:
        with self.sessions.begin() as session:
            row = RiskAssessmentRow(event_id=event_id, vision_analysis_id=vision_analysis_id,
                                    predicted_level=predicted_level, probabilities=probabilities,
                                    model_version=model_version, model_checksum=model_checksum,
                                    mapping_version=mapping_version,
                                    threshold_policy_version=threshold_policy_version)
            session.add(row)
            event = session.get(EventRow, event_id)
            if event:
                event.risk_level, event.risk_probability = predicted_level, probabilities
                event.alert_status = "pending" if predicted_level == "high" else "not_required"
            session.flush()
            if predicted_level == "high":
                task = session.scalar(select(OperatorTaskRow).where(
                    OperatorTaskRow.risk_assessment_id == row.id, OperatorTaskRow.mode == "shadow"))
                if not task:
                    session.add(OperatorTaskRow(event_id=event_id, risk_assessment_id=row.id, mode="shadow"))
            self._schedule_qdrant_index(session, event_id)
            return row

    def schedule_risk_backfill(self, model_version: str) -> int:
        """Queue only the latest described event state not yet scored by a release.

        The event/kind unique outbox key is reopened in place, so repeated
        backfills do not create duplicate work or duplicate assessments.
        """
        with self.sessions.begin() as session:
            latest: dict[str, VisionAnalysisRow] = {}
            for vision in session.scalars(select(VisionAnalysisRow).order_by(
                    VisionAnalysisRow.event_id, VisionAnalysisRow.id.desc())):
                latest.setdefault(vision.event_id, vision)
            now = datetime.now(UTC)
            scheduled = 0
            for event_id, vision in latest.items():
                already_scored = session.scalar(select(RiskAssessmentRow.id).where(
                    RiskAssessmentRow.event_id == event_id,
                    RiskAssessmentRow.vision_analysis_id == vision.id,
                    RiskAssessmentRow.model_version == model_version,
                ))
                if already_scored:
                    continue
                job = session.scalar(select(OutboxRow).where(
                    OutboxRow.event_id == event_id, OutboxRow.kind == "risk"
                ))
                if job:
                    job.status, job.attempts, job.available_at, job.locked_at, job.last_error = (
                        "pending", 0, now, None, ""
                    )
                else:
                    session.add(OutboxRow(event_id=event_id, kind="risk"))
                scheduled += 1
            return scheduled

    @staticmethod
    def _schedule_qdrant_index(session, event_id: str) -> None:
        """Schedule an update while preserving a concurrent worker's revision."""
        job = session.scalar(select(OutboxRow).where(
            OutboxRow.event_id == event_id, OutboxRow.kind == "qdrant"
        ))
        now = datetime.now(UTC)
        if not job:
            session.add(OutboxRow(event_id=event_id, kind="qdrant", revision=1))
            return
        job.revision += 1
        job.attempts, job.available_at, job.last_error = 0, now, ""
        if job.status != "processing":
            job.status, job.locked_at = "pending", None

    def schedule_qdrant_backfill(self) -> int:
        """Requeue every stored event that already has a usable vision description."""
        with self.sessions.begin() as session:
            event_ids = list(session.scalars(select(EventRow.event_id).where(
                EventRow.description.is_not(None), func.trim(EventRow.description) != ""
            )))
            for event_id in event_ids:
                self._schedule_qdrant_index(session, event_id)
            return len(event_ids)

    def requeue_dead_qdrant_jobs(self) -> int:
        with self.sessions.begin() as session:
            jobs = list(session.scalars(select(OutboxRow).where(
                OutboxRow.kind == "qdrant", OutboxRow.status == "dead"
            )))
            now = datetime.now(UTC)
            for job in jobs:
                job.status, job.attempts, job.available_at, job.locked_at, job.last_error = (
                    "pending", 0, now, None, ""
                )
            return len(jobs)

    def complete_qdrant_job(self, job_id: int, claimed_revision: int) -> bool:
        """Complete only the revision that was indexed; otherwise request another upsert."""
        with self.sessions.begin() as session:
            job = session.get(OutboxRow, job_id)
            if not job:
                return False
            if job.revision != claimed_revision:
                job.status, job.attempts, job.available_at, job.locked_at, job.last_error = (
                    "pending", 0, datetime.now(UTC), None, ""
                )
                return False
            job.status, job.locked_at, job.last_error = "completed", None, ""
            return True

    def fail_qdrant_job(self, job_id: int, claimed_revision: int, error: str,
                         max_attempts: int) -> None:
        with self.sessions.begin() as session:
            job = session.get(OutboxRow, job_id)
            if not job:
                return
            if job.revision != claimed_revision:
                job.status, job.attempts, job.available_at, job.locked_at, job.last_error = (
                    "pending", 0, datetime.now(UTC), None, ""
                )
                return
            job.last_error, job.locked_at = error[:4000], None
            if job.attempts >= max_attempts:
                job.status = "dead"
            else:
                job.status = "pending"
                job.available_at = datetime.now(UTC) + timedelta(seconds=2 ** job.attempts)

    def qdrant_index_data(self, event_id: str) -> tuple[EventRow, VisionAnalysisRow, RiskAssessmentRow | None] | None:
        with self.sessions() as session:
            event = session.get(EventRow, event_id)
            if not event or not event.description or not event.description.strip():
                return None
            vision = session.scalar(select(VisionAnalysisRow).where(
                VisionAnalysisRow.event_id == event_id
            ).order_by(VisionAnalysisRow.id.desc()))
            if not vision:
                return None
            risk = session.scalar(select(RiskAssessmentRow).where(
                RiskAssessmentRow.event_id == event_id
            ).order_by(RiskAssessmentRow.id.desc()))
            return event, vision, risk

    def decide_task(self, task_id: int, action: str, label: str | None, note: str,
                    actor_user_id: int, actor_username: str) -> OperatorTaskRow | None:
        with self.sessions.begin() as session:
            task = session.get(OperatorTaskRow, task_id)
            if not task or task.mode != "shadow" or task.status != "pending":
                return None
            old_status = task.status
            new_status = {"confirm": "confirmed", "reject": "rejected", "label": "reviewed"}.get(action)
            if not new_status:
                raise ValueError("unsupported operator action")
            task.status, task.operator_label, task.operator_note = new_status, label, note
            task.decided_at = datetime.now(UTC)
            event = session.get(EventRow, task.event_id)
            if event and action in {"confirm", "reject"}:
                event.alert_status = new_status
                event.operator_note = note
            session.add(OperatorDecisionAuditRow(task_id=task.id, event_id=task.event_id,
                risk_assessment_id=task.risk_assessment_id, action=action, label=label,
                actor_user_id=actor_user_id, actor_username=actor_username, note=note,
                previous_status=old_status, new_status=new_status))
            return task

    def list_events_page(self, limit: int, cursor: tuple[datetime, str] | None = None) -> tuple[list[dict], tuple[datetime, str] | None]:
        with self.sessions() as session:
            statement = select(EventRow).order_by(EventRow.occurred_at.desc(), EventRow.event_id.desc()).limit(limit + 1)
            if cursor:
                timestamp, event_id = cursor
                statement = statement.where(or_(EventRow.occurred_at < timestamp,
                    (EventRow.occurred_at == timestamp) & (EventRow.event_id < event_id)))
            events = list(session.scalars(statement))
            next_cursor = None
            if len(events) > limit:
                events.pop()
                marker = events[-1]
                next_cursor = (marker.occurred_at, marker.event_id)
            return self._cards(session, events), next_cursor

    @staticmethod
    def _cards(session, events: list[EventRow]) -> list[dict]:
        cards: list[dict] = []
        for event in events:
            assessment = session.scalar(select(RiskAssessmentRow).where(
                RiskAssessmentRow.event_id == event.event_id).order_by(RiskAssessmentRow.id.desc()))
            task = None
            if assessment:
                task = session.scalar(select(OperatorTaskRow).where(
                    OperatorTaskRow.risk_assessment_id == assessment.id).order_by(OperatorTaskRow.id.desc()))
            cards.append({"event": event, "assessment": assessment, "task": task})
        return cards

    def list_event_cards(self, limit: int = 10) -> list[dict]:
        with self.sessions() as session:
            events = list(session.scalars(select(EventRow).order_by(EventRow.occurred_at.desc()).limit(limit)))
            return self._cards(session, events)

    def list_high_tasks(self, limit: int, cursor: int | None = None, status: str = "pending") -> tuple[list[dict], int | None]:
        with self.sessions() as session:
            statement = (select(OperatorTaskRow).join(RiskAssessmentRow, OperatorTaskRow.risk_assessment_id == RiskAssessmentRow.id)
                         .where(RiskAssessmentRow.predicted_level == "high", OperatorTaskRow.status == status)
                         .order_by(OperatorTaskRow.id.desc()).limit(limit + 1))
            if cursor:
                statement = statement.where(OperatorTaskRow.id < cursor)
            tasks = list(session.scalars(statement))
            next_cursor = None
            if len(tasks) > limit:
                tasks.pop()
                next_cursor = tasks[-1].id
            return [{"task": task, "event": session.get(EventRow, task.event_id),
                     "assessment": session.get(RiskAssessmentRow, task.risk_assessment_id)} for task in tasks], next_cursor

    def pending_high_task_for_event(self, event_id: str) -> OperatorTaskRow | None:
        with self.sessions() as session:
            return session.scalar(select(OperatorTaskRow).join(
                RiskAssessmentRow, OperatorTaskRow.risk_assessment_id == RiskAssessmentRow.id
            ).where(OperatorTaskRow.event_id == event_id, OperatorTaskRow.status == "pending",
                    RiskAssessmentRow.predicted_level == "high").order_by(OperatorTaskRow.id.desc()))

    def create_user(self, username: str, password_hash: str, role: str) -> UserRow:
        with self.sessions.begin() as session:
            row = UserRow(username=username, password_hash=password_hash, role=role)
            session.add(row)
            session.flush()
            return row

    def authenticate_user(self, username: str, password: str):
        from surveillance.security import verify_password
        with self.sessions() as session:
            user = session.scalar(select(UserRow).where(UserRow.username == username, UserRow.active.is_(True)))
            if not user or not verify_password(password, user.password_hash):
                return None
            return user

    def create_session(self, token_hash: str, user_id: int, expires_at: datetime, idle_expires_at: datetime) -> None:
        with self.sessions.begin() as session:
            session.add(AuthSessionRow(token_hash=token_hash, user_id=user_id, expires_at=expires_at,
                idle_expires_at=idle_expires_at))

    def session_user(self, token_hash: str, idle_seconds: int):
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            auth = session.get(AuthSessionRow, token_hash)
            if not auth or auth.revoked_at or auth.expires_at <= now or auth.idle_expires_at <= now:
                return None
            user = session.get(UserRow, auth.user_id)
            if not user or not user.active:
                return None
            auth.last_seen_at, auth.idle_expires_at = now, now + timedelta(seconds=idle_seconds)
            return user

    def revoke_session(self, token_hash: str) -> None:
        with self.sessions.begin() as session:
            auth = session.get(AuthSessionRow, token_hash)
            if auth and not auth.revoked_at:
                auth.revoked_at = datetime.now(UTC)

    def register_model_release(self, **values) -> ModelReleaseRow:
        with self.sessions.begin() as session:
            row = ModelReleaseRow(**values)
            session.add(row)
            session.flush()
            return row

    def add_model_evaluation(self, release_id: int, **values) -> ModelEvaluationRow:
        with self.sessions.begin() as session:
            row = ModelEvaluationRow(release_id=release_id, **values)
            session.add(row)
            return row

    def list_model_releases(self) -> list[ModelReleaseRow]:
        with self.sessions() as session:
            return list(session.scalars(select(ModelReleaseRow).order_by(ModelReleaseRow.id.desc())))

    def approve_model_release(self, release_id: int, actor: str) -> ModelReleaseRow | None:
        with self.sessions.begin() as session:
            release = session.get(ModelReleaseRow, release_id)
            evaluation = session.scalar(select(ModelEvaluationRow).where(ModelEvaluationRow.release_id == release_id)
                                        .order_by(ModelEvaluationRow.id.desc()))
            if not release or release.status != "draft" or not evaluation or evaluation.language != "ru" or \
                    evaluation.sample_count < 50 or evaluation.macro_f1 < .60 or evaluation.high_recall < .75:
                return None
            for approved in session.scalars(select(ModelReleaseRow).where(ModelReleaseRow.status == "approved")):
                approved.status = "revoked"
                approved.revoked_by, approved.revoked_at, approved.revoke_reason = actor, datetime.now(UTC), "superseded"
            release.status, release.approved_by, release.approved_at = "approved", actor, datetime.now(UTC)
            return release

    def revoke_model_release(self, release_id: int, actor: str, reason: str) -> ModelReleaseRow | None:
        with self.sessions.begin() as session:
            release = session.get(ModelReleaseRow, release_id)
            if not release or release.status != "approved":
                return None
            release.status, release.revoked_by, release.revoked_at, release.revoke_reason = "revoked", actor, datetime.now(UTC), reason
            return release

    def is_approved_model_release(self, version: str, checksum: str, mapping: str, policy: str) -> bool:
        with self.sessions() as session:
            return bool(session.scalar(select(ModelReleaseRow.id).where(ModelReleaseRow.status == "approved",
                ModelReleaseRow.version == version, ModelReleaseRow.checksum == checksum,
                ModelReleaseRow.mapping_version == mapping, ModelReleaseRow.threshold_policy_version == policy)))

    def write_query_audit(self, request_hash: str, route: str, operation: str | None,
                          filters: dict, outcome: str, latency_ms: int, result_count: int,
                          error_code: str | None = None) -> None:
        """The raw user question is deliberately never persisted."""
        with self.sessions.begin() as session:
            session.add(QueryAuditLogRow(request_hash=request_hash, route=route, operation=operation,
                filters=filters, outcome=outcome, latency_ms=latency_ms, result_count=result_count,
                error_code=error_code))
