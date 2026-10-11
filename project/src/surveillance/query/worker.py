import logging
import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import redis

from surveillance.query.broker import REQUEST_STREAM, RedisQueryBroker
from surveillance.query.models import QueryResult, QueryRoute
from surveillance.query.sql_operations import validate_filters

logger = logging.getLogger(__name__)
GROUP = "surveillance-query-host"


class QueryWorker:
    def __init__(self, broker: RedisQueryBroker, intent_client: object, semantic: object, analytics: object,
                 gate: object, timezone_name: str, max_range_days: int, list_limit: int) -> None:
        self.broker, self.intent_client, self.semantic = broker, intent_client, semantic
        self.analytics, self.gate = analytics, gate
        self.timezone_name, self.max_range_days, self.list_limit = timezone_name, max_range_days, list_limit
        self.consumer = f"query-{uuid4()}"

    def ensure_group(self) -> None:
        try:
            self.broker.client.xgroup_create(REQUEST_STREAM, GROUP, id="0-0", mkstream=True)
        except redis.ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    @staticmethod
    def _fallback(evidence, data: dict) -> str:
        if "count" in data:
            return f"За указанный период найдено событий: {data['count']}."
        if evidence:
            return "Найдены события: " + ", ".join(item.event_id for item in evidence[:3]) + "."
        return "По заданным условиям событий не найдено."

    def _summary(self, question: str, evidence, data: dict) -> tuple[str, list[str]]:
        try:
            result = self.intent_client.summarize(question, [item.model_dump(mode="json") for item in evidence], data)
            allowed = {item.event_id for item in evidence}
            if not set(result.cited_event_ids).issubset(allowed):
                raise ValueError("summary cited an unknown event")
            return result.answer_ru, result.cited_event_ids
        except Exception:
            logger.warning("grounded summary unavailable; using deterministic fallback", exc_info=True)
            return self._fallback(evidence, data), [item.event_id for item in evidence[:3]]

    def process(self, request_id: str, question: str) -> QueryResult:
        started = time.monotonic()
        now = datetime.now(ZoneInfo(self.timezone_name))
        try:
            with self.gate.hold() as acquired:
                if not acquired:
                    return QueryResult(request_id=request_id, route=QueryRoute.vector,
                        error_code="worker_busy", meta={"duration_ms": 0})
                intent = self.intent_client.parse_intent(question, now)
            if intent.route == QueryRoute.clarification:
                return QueryResult(request_id=request_id, route=QueryRoute.clarification,
                    missing_fields=intent.missing_fields,
                    meta={"operation": None, "duration_ms": int((time.monotonic()-started)*1000)})
            if intent.route == QueryRoute.vector:
                with self.gate.hold() as acquired:
                    if not acquired:
                        return QueryResult(request_id=request_id, route=QueryRoute.vector,
                            error_code="worker_busy", meta={"duration_ms": 0})
                    evidence = self.semantic.search(intent.semantic_query or question, intent.filters)
                    answer, citations = self._summary(question, evidence, {})
                return QueryResult(request_id=request_id, route=QueryRoute.vector, answer_ru=answer,
                    evidence=evidence, meta={"operation": "semantic", "citations": citations,
                    "filters": intent.filters.model_dump(mode="json", exclude_none=True),
                    "duration_ms": int((time.monotonic()-started)*1000)})
            filters = validate_filters(intent.filters, self.max_range_days, self.timezone_name)
            data = self.analytics.execute(intent.operation, filters, self.list_limit)
            evidence = self.analytics.evidence_for_filters(filters)
            with self.gate.hold() as acquired:
                answer, citations = (self._summary(question, evidence, data) if acquired
                                     else (self._fallback(evidence, data), [e.event_id for e in evidence[:3]]))
            return QueryResult(request_id=request_id, route=QueryRoute.sql, answer_ru=answer,
                evidence=evidence, data=data, meta={"operation": intent.operation.value, "citations": citations,
                "filters": filters.model_dump(mode="json", exclude_none=True),
                "duration_ms": int((time.monotonic()-started)*1000)})
        except ValueError as error:
            return QueryResult(request_id=request_id, route=QueryRoute.clarification,
                missing_fields=["period"] if "period" in str(error) else [], error_code="clarification_required",
                meta={"duration_ms": int((time.monotonic()-started)*1000)})
        except Exception:
            logger.exception("query worker failed")
            return QueryResult(request_id=request_id, route=QueryRoute.vector, error_code="dependency_unavailable",
                meta={"duration_ms": int((time.monotonic()-started)*1000)})

    def _handle(self, message: dict) -> None:
        request_id, question = message.get("request_id"), message.get("request")
        if not request_id or not question:
            return
        result = self.process(request_id, question)
        self.broker.publish_result(request_id, result.model_dump(mode="json"))

    def run_once(self, block_ms: int = 1000) -> bool:
        self.ensure_group()
        # Recover one abandoned message before requesting new work.  It is acknowledged only
        # after the result key has been written, so a worker crash cannot silently lose it.
        claimed = self.broker.client.xautoclaim(REQUEST_STREAM, GROUP, self.consumer,
                                                min_idle_time=300_000, start_id="0-0", count=1)
        reclaimed = claimed[1] if claimed and len(claimed) > 1 else []
        if reclaimed:
            message_id, message = reclaimed[0]
            self._handle(message)
            self.broker.client.xack(REQUEST_STREAM, GROUP, message_id)
            return True
        response = self.broker.client.xreadgroup(GROUP, self.consumer, {REQUEST_STREAM: ">"}, count=1, block=block_ms)
        if not response:
            return False
        stream, messages = response[0]
        message_id, message = messages[0]
        self._handle(message)
        self.broker.client.xack(stream, GROUP, message_id)
        return True

    def run_forever(self, poll_seconds: float) -> None:
        self.ensure_group()
        while True:
            self.run_once(max(1, int(poll_seconds * 1000)))
