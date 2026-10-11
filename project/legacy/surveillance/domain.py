from datetime import datetime
from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class AlertStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


class EventCreate(BaseModel):
    event_id: UUID
    camera_id: str = Field(pattern=r"^camera-[1-4]$")
    track_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    object_type: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)
    bbox: list[int] = Field(min_length=4, max_length=4)
    media_uri: str = ""
    model_version: str


class Question(BaseModel):
    request: str = Field(min_length=1, max_length=1000)


class AlertDecision(BaseModel):
    status: AlertStatus
    note: str = Field(default="", max_length=1000)
