import re
from enum import StrEnum


class QueryTarget(StrEnum):
    vector = "vector"
    sql = "sql"


class QueryRouter:
    """Routes exact counts/time intervals to SQL; conceptual questions to Qdrant."""

    _sql_markers = re.compile(r"\b(сколько|число|за\s+последн|сегодня|вчера|час|минут|день|дат)\b", re.I)

    def route(self, request: str) -> QueryTarget:
        return QueryTarget.sql if self._sql_markers.search(request) else QueryTarget.vector
