from datetime import UTC, datetime, timedelta

from surveillance.camera.deduplication import RedisPresenceDeduplicator, PresenceDeduplicator, deduplication_key
from surveillance.camera.models import TrackedObject


def test_same_track_creates_one_event_for_long_presence() -> None:
    now = datetime.now(UTC)
    track = TrackedObject("42", "person", 0.9, (1, 2, 10, 20), now, now)
    dedupe = PresenceDeduplicator()

    assert dedupe.allow("local-camera", track, now)
    for second in range(1, 1001):
        assert not dedupe.allow("local-camera", track, now + timedelta(seconds=second))


def test_different_track_creates_a_new_event() -> None:
    now = datetime.now(UTC)
    dedupe = PresenceDeduplicator()
    first = TrackedObject("42", "person", 0.9, (1, 2, 10, 20), now, now)
    second = TrackedObject("43", "person", 0.9, (1, 2, 10, 20), now, now)

    assert dedupe.allow("local-camera", first, now)
    assert dedupe.allow("local-camera", second, now)


def test_database_key_is_stable_for_entire_track_lifecycle() -> None:
    now = datetime(2026, 10, 7, 12, 0, 5, tzinfo=UTC)
    track = TrackedObject("42", "person", 0.9, (1, 2, 10, 20), now, now)
    assert deduplication_key("local-camera", track) == deduplication_key("local-camera", track)


def test_new_presence_has_a_new_database_key() -> None:
    now = datetime(2026, 10, 7, 12, 0, 5, tzinfo=UTC)
    first = TrackedObject("42", "person", 0.9, (1, 2, 10, 20), now, now)
    second = TrackedObject("42", "person", 0.9, (1, 2, 10, 20), now + timedelta(minutes=1), now)
    assert deduplication_key("local-camera", first) != deduplication_key("local-camera", second)


def test_redis_presence_ttl_is_refreshed_while_object_is_visible() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.keys: set[str] = set()
            self.expirations: list[int] = []

        def set(self, key, _value, *, nx, ex):
            assert nx is True
            if key in self.keys:
                return False
            self.keys.add(key)
            self.expirations.append(ex)
            return True

        def expire(self, _key, seconds):
            self.expirations.append(seconds)
            return True

    now = datetime.now(UTC)
    track = TrackedObject("42", "person", 0.9, (1, 2, 10, 20), now, now)
    dedupe = RedisPresenceDeduplicator.__new__(RedisPresenceDeduplicator)
    dedupe.client = FakeRedis()
    dedupe.absence_timeout_seconds = 20

    assert dedupe.allow("local-camera", track, now)
    assert not dedupe.allow("local-camera", track, now + timedelta(minutes=10))
    assert dedupe.client.expirations == [20, 20]

    new_presence = TrackedObject(
        "42", "person", 0.9, (1, 2, 10, 20), now + timedelta(minutes=11), now
    )
    assert dedupe.allow("local-camera", new_presence, now + timedelta(minutes=11))
