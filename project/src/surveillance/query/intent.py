"""Strict, text-only Ollama contracts for query routing and grounded summaries."""

import json
import re
from datetime import datetime, timedelta

import httpx

from surveillance.query.models import AnalyticsOperation, QueryFilters, QueryIntent, QueryRoute, SummaryPayload


class QueryModelUnavailableError(RuntimeError):
    pass


class OllamaQueryClient:
    def __init__(self, host: str, model: str, intent_timeout: float, summary_timeout: float,
                 client: httpx.Client | None = None) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.intent_timeout = intent_timeout
        self.summary_timeout = summary_timeout
        self.client = client or httpx.Client()

    def _chat(self, messages: list[dict], schema: dict, timeout: float) -> dict:
        try:
            response = self.client.post(
                f"{self.host}/api/chat",
                json={"model": self.model, "stream": False, "keep_alive": "0",
                      "format": schema, "options": {"temperature": 0}, "messages": messages},
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return json.loads(content)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise QueryModelUnavailableError("Ollama returned no valid structured query result") from error

    def parse_intent(self, question: str, now: datetime) -> QueryIntent:
        system = (
            "Ты маршрутизатор запросов видеонаблюдения. Верни только JSON по схеме. "
            "Никогда не пиши SQL, таблицы, имена колонок или инструкции. "
            "Общий вопрос о произошедшем — route=vector. Количество, список или группировка — route=sql. "
            "ВСЕГДА заполняй обязательные поля для выбранного route: "
            "для vector обязательно semantic_query — точная краткая формулировка вопроса; "
            "для sql обязательно operation и filters со start_at/end_at. "
            "Для route=sql обязательны start_at и end_at с offset +03:00; если периода нет, "
            "верни route=clarification и missing_fields=['period']. "
            "Допустимы только операции count_events, list_events, group_by_hour, group_by_object_type. "
            "'Сколько ...' означает count_events, 'покажи события ...' означает list_events, "
            "'по часам' означает group_by_hour, 'каждого типа' или 'по типам' означает group_by_object_type. "
            "Для vector filters можно не указывать, но semantic_query обязателен. "
            "object_type должен быть каноническим COCO названием на английском, если он известен. "
            f"Текущее время в Москве: {now.isoformat()}."
        )
        # Qwen is an assistant, not a policy engine.  First recognize the small,
        # explicit analytics language that this product supports.  This prevents a
        # plausible-but-invalid LLM reply from turning a clear request into an
        # unnecessary clarification, and never produces arbitrary SQL.
        deterministic = self._known_analytics_intent(question, now)
        if deterministic is not None:
            return deterministic
        try:
            raw = self._chat(
                [{"role": "system", "content": system}, {"role": "user", "content": question}],
                QueryIntent.model_json_schema(), self.intent_timeout,
            )
            return QueryIntent.model_validate(raw)
        except (QueryModelUnavailableError, ValueError):
            # A general question is still safe to search semantically.  It does
            # not grant database access or create a SQL operation.
            return QueryIntent(route=QueryRoute.vector, semantic_query=question)

    @staticmethod
    def _known_analytics_intent(question: str, now: datetime) -> QueryIntent | None:
        """Create only allowlisted operations for unambiguous Russian requests."""
        text = question.casefold()
        operation: AnalyticsOperation | None = None
        if re.search(r"\bпо\s+час", text):
            operation = AnalyticsOperation.group_by_hour
        elif re.search(r"\b(кажд\w*\s+тип|по\s+тип)\w*", text):
            operation = AnalyticsOperation.group_by_object_type
        elif re.search(r"\b(сколько|количество|посчитай)\b", text):
            operation = AnalyticsOperation.count_events
        elif re.search(r"\b(покажи|выведи|список|какие)\b", text):
            operation = AnalyticsOperation.list_events
        if operation is None:
            return None

        filters = QueryFilters(
            camera_id=OllamaQueryClient._camera_id(text),
            object_type=OllamaQueryClient._object_type(text),
            start_at=None,
            end_at=None,
        )
        period = OllamaQueryClient._period(text, now)
        if period is None:
            return QueryIntent(route=QueryRoute.clarification, missing_fields=["period"])
        return QueryIntent(route=QueryRoute.sql, operation=operation,
                           filters=filters.model_copy(update={"start_at": period[0], "end_at": period[1]}))

    @staticmethod
    def _period(text: str, now: datetime) -> tuple[datetime, datetime] | None:
        hours = re.search(r"последн\w*\s+(\d+)\s*час", text)
        if hours:
            return now - timedelta(hours=int(hours.group(1))), now
        days = re.search(r"последн\w*\s+(\d+)\s*(?:дн|сут)", text)
        if days:
            return now - timedelta(days=int(days.group(1))), now
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if "сегодня" in text:
            return today, now
        if "вчера" in text:
            return today - timedelta(days=1), today
        return None

    @staticmethod
    def _object_type(text: str) -> str | None:
        if re.search(r"\b(машин|автомобил|авто)\w*", text):
            return "car"
        if re.search(r"\b(люд|человек)\w*", text):
            return "person"
        return None

    @staticmethod
    def _camera_id(text: str) -> str | None:
        match = re.search(r"\bкамер[аы]\s+([a-z0-9_-]+)", text)
        return match.group(1) if match else None

    def summarize(self, question: str, evidence: list[dict], data: dict) -> SummaryPayload:
        allowed = [item["event_id"] for item in evidence]
        context = {"question": question, "evidence": evidence, "data": data,
                   "allowed_event_ids": allowed}
        system = (
            "Составь короткий русский ответ только по переданным данным. Не добавляй факты. "
            "cited_event_ids могут содержать только ID из allowed_event_ids. Если доказательств нет, "
            "так и скажи. Верни исключительно JSON по схеме."
        )
        raw = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(context, default=str)}],
            SummaryPayload.model_json_schema(), self.summary_timeout,
        )
        return SummaryPayload.model_validate(raw)
