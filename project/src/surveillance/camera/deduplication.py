import hashlib
from datetime import datetime
from math import ceil

from redis import Redis

from surveillance.camera.models import TrackedObject


class PresenceDeduplicator:
    """Creates one event for one stable track lifecycle."""

    def __init__(self) -> None:
        self._observations: set[str] = set()

    def allow(self, camera_id: str, track: TrackedObject, now: datetime) -> bool:
        del now
        key = deduplication_key(camera_id, track)
        if key in self._observations:
            return False
        self._observations.add(key)
        return True


def deduplication_key(camera_id: str, track: TrackedObject) -> str:
    """Stable key for a single continuous presence, independent of wall-clock buckets."""
    first_seen = track.first_seen_at.isoformat(timespec="microseconds")
    identity = f"{camera_id}\x1f{track.track_id}\x1f{track.label}\x1f{first_seen}"
    return f"presence:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


class RedisPresenceDeduplicator:
    """Cross-process presence guard whose TTL is refreshed while a track remains visible."""

    def __init__(self, redis_url: str, absence_timeout_seconds: float) -> None:
        self.client = Redis.from_url(redis_url)
        self.absence_timeout_seconds = max(1, ceil(absence_timeout_seconds))

    def allow(self, camera_id: str, track: TrackedObject, now: datetime) -> bool:
        del now
        first_seen = track.first_seen_at.isoformat(timespec="microseconds")
        identity = f"{camera_id}\x1f{track.track_id}\x1f{track.label}\x1f{first_seen}"
        key = f"camera:presence:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"
        created = bool(self.client.set(key, "1", nx=True, ex=self.absence_timeout_seconds))
        if not created:
            self.client.expire(key, self.absence_timeout_seconds)
        return created
