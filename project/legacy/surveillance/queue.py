import json
from redis import Redis


class TaskQueue:
    def __init__(self, url: str, queue_name: str = "vision-events"):
        self.client = Redis.from_url(url, decode_responses=True)
        self.queue_name = queue_name

    def publish(self, event_id: str) -> None:
        self.client.rpush(self.queue_name, json.dumps({"event_id": event_id}))

    def consume(self, timeout_seconds: int = 5) -> str | None:
        result = self.client.blpop(self.queue_name, timeout=timeout_seconds)
        return json.loads(result[1])["event_id"] if result else None
