"""Fixed, parameterised analytics SELECT statements; no model-generated SQL is accepted."""

from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Column, DateTime, Float, MetaData, String, Table, func, select

from surveillance.query.models import AnalyticsOperation, QueryFilters

metadata = MetaData()
analytics_events = Table(
    "analytics_events", metadata,
    Column("event_id", String), Column("camera_id", String), Column("occurred_at", DateTime(timezone=True)),
    Column("object_type", String), Column("confidence", Float), Column("description", String),
    Column("risk_level", String), Column("alert_status", String), Column("model_version", String),
)


def validate_filters(filters: QueryFilters, max_days: int, timezone_name: str) -> QueryFilters:
    if not filters.start_at or not filters.end_at:
        raise ValueError("analytics period is required")
    zone = ZoneInfo(timezone_name)
    start = filters.start_at.astimezone(zone)
    end = filters.end_at.astimezone(zone)
    if end - start > timedelta(days=max_days):
        raise ValueError(f"analytics period cannot exceed {max_days} days")
    return filters.model_copy(update={"start_at": start.astimezone(UTC), "end_at": end.astimezone(UTC)})


def conditions(filters: QueryFilters):
    clauses = [analytics_events.c.occurred_at >= filters.start_at,
               analytics_events.c.occurred_at < filters.end_at]
    for name in ("camera_id", "object_type", "risk_level"):
        value = getattr(filters, name)
        if value:
            clauses.append(getattr(analytics_events.c, name) == value)
    return clauses


def build_statement(operation: AnalyticsOperation, filters: QueryFilters, list_limit: int):
    where = conditions(filters)
    if operation == AnalyticsOperation.count_events:
        return select(func.count().label("count")).select_from(analytics_events).where(*where)
    if operation == AnalyticsOperation.list_events:
        return select(analytics_events).where(*where).order_by(analytics_events.c.occurred_at.desc()).limit(list_limit)
    if operation == AnalyticsOperation.group_by_hour:
        hour = func.date_trunc("hour", analytics_events.c.occurred_at).label("hour")
        return select(hour, func.count().label("count")).where(*where).group_by(hour).order_by(hour).limit(744)
    if operation == AnalyticsOperation.group_by_object_type:
        return select(analytics_events.c.object_type, func.count().label("count")).where(*where).group_by(
            analytics_events.c.object_type).order_by(func.count().desc()).limit(80)
    raise ValueError("operation is not allowlisted")
