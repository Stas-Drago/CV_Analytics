from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from surveillance.query.models import AnalyticsOperation, Evidence, QueryFilters, QueryIntent, QueryRoute, SummaryPayload
from surveillance.query.intent import OllamaQueryClient
from surveillance.query.sql_operations import build_statement, validate_filters
from surveillance.query.worker import QueryWorker
from surveillance.api.app import create_app


MOSCOW = ZoneInfo("Europe/Moscow")


def interval(hours: int = 3) -> QueryFilters:
    end = datetime(2026, 10, 10, 12, tzinfo=MOSCOW)
    return QueryFilters(start_at=end - timedelta(hours=hours), end_at=end)


def test_intent_rejects_sql_and_extra_fields() -> None:
    with pytest.raises(Exception):
        QueryIntent.model_validate({"route": "sql", "operation": "DROP TABLE events", "filters": {}})
    with pytest.raises(Exception):
        QueryIntent.model_validate({"route": "vector", "semantic_query": "тест", "sql": "SELECT 1"})
    with pytest.raises(Exception, match="COCO"):
        QueryFilters(object_type="not-a-yolo-class")


def test_analytics_period_is_moscow_normalized_and_bounded() -> None:
    normalized = validate_filters(interval(), 31, "Europe/Moscow")
    assert normalized.start_at.utcoffset() == timedelta(0)
    with pytest.raises(ValueError, match="31"):
        validate_filters(interval(32 * 24), 31, "Europe/Moscow")


def test_all_sql_operations_are_fixed_selects_with_bound_parameters() -> None:
    for operation in AnalyticsOperation:
        compiled = build_statement(operation, validate_filters(interval(), 31, "Europe/Moscow"), 100).compile(
            dialect=postgresql.dialect()
        )
        assert compiled.string.lstrip().upper().startswith("SELECT")
        assert "DROP" not in compiled.string.upper()
        assert compiled.params


class Gate:
    class Hold:
        def __enter__(self): return True
        def __exit__(self, *_args): return False
    def hold(self): return self.Hold()


class IntentClient:
    def __init__(self, intent, summary=None): self.intent, self.summary_value = intent, summary
    def parse_intent(self, *_args): return self.intent
    def summarize(self, *_args): return self.summary_value or SummaryPayload(answer_ru="Готово", cited_event_ids=[])


class Semantic:
    def search(self, *_args):
        return [Evidence(event_id="e1", camera_id="camera", occurred_at=datetime.now(MOSCOW),
                         object_type="car", description="Автомобиль", score=0.9)]


class Analytics:
    def execute(self, *_args): return {"count": 2}
    def evidence_for_filters(self, *_args): return []


def worker(intent, summary=None):
    return QueryWorker(object(), IntentClient(intent, summary), Semantic(), Analytics(), Gate(),
                       "Europe/Moscow", 31, 100)


def test_semantic_result_uses_only_known_citations() -> None:
    result = worker(QueryIntent(route="vector", semantic_query="подозрительное"),
                    SummaryPayload(answer_ru="Ответ", cited_event_ids=["e1"])).process("r1", "вопрос")
    assert result.route == QueryRoute.vector
    assert result.meta["citations"] == ["e1"]


def test_unknown_summary_citation_gets_deterministic_fallback() -> None:
    result = worker(QueryIntent(route="vector", semantic_query="подозрительное"),
                    SummaryPayload(answer_ru="Ответ", cited_event_ids=["other"])).process("r1", "вопрос")
    assert result.answer_ru.startswith("Найдены события")
    assert result.meta["citations"] == ["e1"]


def test_count_requires_time_range_at_contract_boundary() -> None:
    with pytest.raises(Exception):
        QueryIntent.model_validate({"route": "sql", "operation": "count_events", "filters": {}})


def test_known_russian_analytics_requests_do_not_depend_on_llm_json() -> None:
    now = datetime(2026, 10, 11, 14, tzinfo=MOSCOW)
    count = OllamaQueryClient._known_analytics_intent("Сколько машин проехало за последние 3 часа?", now)
    listing = OllamaQueryClient._known_analytics_intent(
        "Покажи события с людьми у камеры local-camera за сегодня.", now
    )
    grouping = OllamaQueryClient._known_analytics_intent("Сколько объектов каждого типа было замечено вчера?", now)
    assert count and count.operation == AnalyticsOperation.count_events
    assert count.filters.object_type == "car"
    assert listing and listing.operation == AnalyticsOperation.list_events
    assert listing.filters.camera_id == "local-camera"
    assert grouping and grouping.operation == AnalyticsOperation.group_by_object_type


def test_api_returns_422_for_worker_clarification(monkeypatch) -> None:
    class Broker:
        def __init__(self, *_args): pass
        def submit_and_wait(self, *_args):
            return {"route": "clarification", "missing_fields": ["period"], "meta": {"duration_ms": 1}}

    class Repo:
        def __init__(self, *_args): pass
        def write_query_audit(self, **kwargs):
            assert kwargs["request_hash"]
            assert "вопрос" not in str(kwargs)

    monkeypatch.setattr("surveillance.api.routes_query.RedisQueryBroker", Broker)
    monkeypatch.setattr("surveillance.api.routes_query.PostgresEventRepository", Repo)
    class SessionRepository:
        def __init__(self, _url): pass
        def session_user(self, *_args):
            from types import SimpleNamespace
            return SimpleNamespace(id=1, username="viewer", role="viewer")

    monkeypatch.setattr("surveillance.api.app.PostgresEventRepository", SessionRepository)
    response = TestClient(create_app()).post("/api/query", json={"request": "Сколько машин?"},
                                               cookies={"surveillance_session": "test"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "clarification_required"
