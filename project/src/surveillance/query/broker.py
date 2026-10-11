import json
import time
from uuid import uuid4

import redis


REQUEST_STREAM = "surveillance:query:requests"
RESULT_PREFIX = "surveillance:query:result:"


class QueryUnavailableError(RuntimeError):
    pass


class QueryTimeoutError(TimeoutError):
    pass


class RedisQueryBroker:
    def __init__(self, redis_url: str, result_ttl_seconds: int, stream_max_length: int) -> None:
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.result_ttl_seconds = result_ttl_seconds
        self.stream_max_length = stream_max_length

    def submit_and_wait(self, request: str, wait_seconds: float) -> dict:
        request_id = str(uuid4())
        try:
            self.client.xadd(REQUEST_STREAM, {"request_id": request_id, "request": request},
                             maxlen=self.stream_max_length, approximate=True)
        except redis.RedisError as error:
            raise QueryUnavailableError("query worker queue is unavailable") from error
        deadline = time.monotonic() + wait_seconds
        key = f"{RESULT_PREFIX}{request_id}"
        while time.monotonic() < deadline:
            try:
                raw = self.client.get(key)
            except redis.RedisError as error:
                raise QueryUnavailableError("query result store is unavailable") from error
            if raw:
                return json.loads(raw)
            time.sleep(0.1)
        raise QueryTimeoutError("query worker did not return a result in time")

    def publish_result(self, request_id: str, result: dict) -> None:
        self.client.setex(f"{RESULT_PREFIX}{request_id}", self.result_ttl_seconds, json.dumps(result, default=str))
