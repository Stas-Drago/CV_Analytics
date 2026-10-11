from uuid import UUID

from sqlalchemy import create_engine, text

from surveillance.query.models import AnalyticsOperation, Evidence, QueryFilters
from surveillance.query.sql_operations import analytics_events, build_statement, conditions


class ReaderAnalyticsRepository:
    """Uses a separate read-only database account and the media-free view only."""

    def __init__(self, database_url: str, timeout_ms: int) -> None:
        if not database_url:
            raise ValueError("ANALYTICS_DATABASE_URL is required for query-worker")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.timeout_ms = timeout_ms

    def _rows(self, statement) -> list[dict]:
        with self.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SELECT set_config('statement_timeout', :value, true)"),
                                   {"value": f"{self.timeout_ms}ms"})
            return [dict(row) for row in connection.execute(statement).mappings()]

    def execute(self, operation: AnalyticsOperation, filters: QueryFilters, list_limit: int) -> dict:
        rows = self._rows(build_statement(operation, filters, list_limit))
        if operation == AnalyticsOperation.count_events:
            return {"count": rows[0]["count"] if rows else 0}
        return {"rows": rows}

    def hydrate(self, ids_and_scores: list[dict]) -> list[Evidence]:
        # Qdrant point IDs are serialized strings while PostgreSQL stores
        # events.event_id as UUID.  Bind UUID values so PostgreSQL does not
        # attempt an invalid uuid = varchar comparison.
        try:
            ids = [UUID(str(item["event_id"])) for item in ids_and_scores]
        except (KeyError, TypeError, ValueError):
            return []
        if not ids:
            return []
        rows = self._rows(analytics_events.select().where(analytics_events.c.event_id.in_(ids)))
        by_id = {str(row["event_id"]): row for row in rows}
        evidence: list[Evidence] = []
        for hit in ids_and_scores:
            row = by_id.get(hit["event_id"])
            if row and row.get("description"):
                evidence.append(Evidence(event_id=str(row["event_id"]), camera_id=row["camera_id"],
                    occurred_at=row["occurred_at"], object_type=row["object_type"],
                    description=row["description"], risk_level=row.get("risk_level"), score=hit["score"]))
        return evidence

    def evidence_for_filters(self, filters: QueryFilters, limit: int = 10) -> list[Evidence]:
        rows = self._rows(analytics_events.select().where(*conditions(filters)).order_by(
            analytics_events.c.occurred_at.desc()).limit(limit))
        return [Evidence(event_id=str(row["event_id"]), camera_id=row["camera_id"],
            occurred_at=row["occurred_at"], object_type=row["object_type"], description=row["description"],
            risk_level=row.get("risk_level")) for row in rows if row.get("description")]
