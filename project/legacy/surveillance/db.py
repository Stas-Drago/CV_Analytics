from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, Float, JSON, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from surveillance.domain import AlertStatus, EventCreate, RiskLevel


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(32), index=True)
    track_id: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    object_type: Mapped[str] = mapped_column(String(100), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    bbox: Mapped[list[int]] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_uri: Mapped[str] = mapped_column(Text, default="")
    model_version: Mapped[str] = mapped_column(String(100))
    risk_level: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    risk_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    vision_risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    vision_risk_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_rationale: Mapped[str] = mapped_column(Text, default="")
    alert_status: Mapped[str] = mapped_column(String(16), default=AlertStatus.pending.value, index=True)
    operator_note: Mapped[str] = mapped_column(Text, default="")


class Repository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def create_event(self, item: EventCreate) -> Event:
        with self.sessions.begin() as session:
            event = session.get(Event, str(item.event_id))
            if event:
                return event
            values = item.model_dump(mode="python")
            values["event_id"] = str(values["event_id"])
            event = Event(**values)
            session.add(event)
            return event

    def list_events(self, *, camera_id: str | None = None, limit: int = 100) -> list[Event]:
        statement = select(Event).order_by(Event.occurred_at.desc()).limit(min(limit, 100))
        if camera_id:
            statement = statement.where(Event.camera_id == camera_id)
        with self.sessions() as session:
            return list(session.scalars(statement))

    def set_alert(self, event_id: UUID, status: AlertStatus, note: str) -> Event | None:
        with self.sessions.begin() as session:
            event = session.get(Event, str(event_id))
            if event:
                event.alert_status, event.operator_note = status.value, note
            return event

    def get_event(self, event_id: str) -> Event | None:
        with self.sessions() as session:
            return session.get(Event, event_id)

    def save_analysis(self, event_id: str, description: str, risk: RiskLevel, probability: float,
                      vision_level: RiskLevel, vision_probability: float, rationale: str) -> Event | None:
        with self.sessions.begin() as session:
            event = session.get(Event, event_id)
            if event:
                event.description = description
                event.risk_level = risk.value
                event.risk_probability = probability
                event.vision_risk_level = vision_level.value
                event.vision_risk_probability = vision_probability
                event.risk_rationale = rationale
            return event
