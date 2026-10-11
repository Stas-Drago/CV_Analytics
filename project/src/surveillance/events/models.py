from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class AlertStatus(StrEnum):
    not_required = "not_required"
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


class DetectedEvent(BaseModel):
    event_id: UUID
    camera_id: str = "local-camera"
    track_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    object_type: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)
    bbox: list[int] = Field(min_length=4, max_length=4)
    frame_jpeg: bytes
    object_crop_jpeg: bytes | None = None
    model_version: str
    deduplication_key: str = Field(min_length=1, max_length=255)


class QueryRequest(BaseModel):
    request: str = Field(min_length=1, max_length=1000)


class ShadowLabelRequest(BaseModel):
    label: RiskLevel
    note: str = Field(default="", max_length=2000)


class DecisionRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=512)


class RevokeModelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
