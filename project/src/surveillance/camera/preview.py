import json

from redis import Redis


class RedisCameraPreview:
    frame_key = "camera:local-camera:latest-frame"
    status_key = "camera:local-camera:status"

    def __init__(self, redis_url: str) -> None:
        self.client = Redis.from_url(redis_url)

    def publish_frame(self, jpeg: bytes) -> None:
        self.client.set(self.frame_key, jpeg, ex=5)

    def publish_status(self, status: dict) -> None:
        ttl = 60 if status.get("state") in {"offline", "error"} else 5
        self.client.set(self.status_key, json.dumps(status), ex=ttl)

    def frame(self) -> bytes | None:
        return self.client.get(self.frame_key)

    def status(self) -> dict:
        value = self.client.get(self.status_key)
        return json.loads(value) if value else {"state": "offline", "error": "camera-ingest is not publishing status"}
