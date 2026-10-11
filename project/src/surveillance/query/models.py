from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


COCO80 = frozenset(
    "person|bicycle|car|motorcycle|airplane|bus|train|truck|boat|traffic light|fire hydrant|"
    "stop sign|parking meter|bench|bird|cat|dog|horse|sheep|cow|elephant|bear|zebra|giraffe|"
    "backpack|umbrella|handbag|tie|suitcase|frisbee|skis|snowboard|sports ball|kite|baseball bat|"
    "baseball glove|skateboard|surfboard|tennis racket|bottle|wine glass|cup|fork|knife|spoon|bowl|"
    "banana|apple|sandwich|orange|broccoli|carrot|hot dog|pizza|donut|cake|chair|couch|potted plant|"
    "bed|dining table|toilet|tv|laptop|mouse|remote|keyboard|cell phone|microwave|oven|toaster|sink|"
    "refrigerator|book|clock|vase|scissors|teddy bear|hair drier|toothbrush".split("|")
)


class QueryRoute(StrEnum):
    vector = "vector"
    sql = "sql"
    clarification = "clarification"


class AnalyticsOperation(StrEnum):
    count_events = "count_events"
    list_events = "list_events"
    group_by_hour = "group_by_hour"
    group_by_object_type = "group_by_object_type"


class QueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: str | None = Field(default=None, max_length=100)
    object_type: str | None = Field(default=None, max_length=100)
    risk_level: str | None = Field(default=None, pattern="^(low|medium|high)$")
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "QueryFilters":
        if self.object_type and self.object_type not in COCO80:
            raise ValueError("object_type must be a COCO-80 class")
        if (self.start_at is None) != (self.end_at is None):
            raise ValueError("start_at and end_at must be supplied together")
        if self.start_at and (self.start_at.tzinfo is None or self.end_at.tzinfo is None):
            raise ValueError("time range must include a timezone")
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        return self


class QueryIntent(BaseModel):
    """The only model-produced contract accepted by the application."""

    model_config = ConfigDict(extra="forbid")

    route: QueryRoute
    operation: AnalyticsOperation | None = None
    semantic_query: str | None = Field(default=None, max_length=1000)
    filters: QueryFilters = Field(default_factory=QueryFilters)
    missing_fields: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_route(self) -> "QueryIntent":
        if self.route == QueryRoute.sql:
            if not self.operation:
                raise ValueError("analytics route requires an operation")
            if not self.filters.start_at or not self.filters.end_at:
                raise ValueError("analytics route requires a time range")
        elif self.route == QueryRoute.vector:
            if not self.semantic_query or not self.semantic_query.strip():
                raise ValueError("vector route requires semantic_query")
            if self.operation:
                raise ValueError("vector route cannot contain an analytics operation")
        elif not self.missing_fields:
            raise ValueError("clarification route requires missing_fields")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    camera_id: str
    occurred_at: datetime
    object_type: str
    description: str
    risk_level: str | None = None
    score: float | None = None


class SummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_ru: str = Field(min_length=1, max_length=1200)
    cited_event_ids: list[str] = Field(default_factory=list, max_length=20)


class QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    route: QueryRoute
    answer_ru: str | None = None
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)
    data: dict = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    error_code: str | None = None
