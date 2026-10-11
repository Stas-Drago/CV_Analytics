from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class TrackedObject:
    track_id: str
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]
    first_seen_at: datetime
    last_seen_at: datetime
