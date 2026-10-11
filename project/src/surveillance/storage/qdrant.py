from qdrant_client import QdrantClient
from qdrant_client.models import (
    DatetimeRange,
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)


DEFAULT_COLLECTION = "surveillance_events_labse_v1"
VECTOR_SIZE = 768


class QdrantEventIndex:
    def __init__(self, url: str, collection: str = DEFAULT_COLLECTION,
                 timeout_seconds: float = 10.0, client: QdrantClient | None = None) -> None:
        self.collection = collection
        self.client = client or QdrantClient(url=url, timeout=timeout_seconds)

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection, VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
            )
            return
        vectors = self.client.get_collection(self.collection).config.params.vectors
        if not isinstance(vectors, VectorParams) or vectors.size != VECTOR_SIZE or vectors.distance != Distance.COSINE:
            raise ValueError(
                f"Qdrant collection {self.collection!r} must use {VECTOR_SIZE}-dimensional COSINE vectors"
            )

    def upsert(self, event_id: str, vector: list[float], payload: dict) -> None:
        if len(vector) != VECTOR_SIZE:
            raise ValueError(f"Qdrant vector must contain {VECTOR_SIZE} values")
        self.client.upsert(self.collection, [PointStruct(id=event_id, vector=vector, payload=payload)])

    def ensure_query_indexes(self) -> None:
        """Create only the indexes needed by query routing, after validating the collection."""
        self.ensure_collection()
        for field, schema in (
            ("camera_id", PayloadSchemaType.KEYWORD),
            ("object_type", PayloadSchemaType.KEYWORD),
            ("risk.level", PayloadSchemaType.KEYWORD),
            ("occurred_at", PayloadSchemaType.DATETIME),
        ):
            self.client.create_payload_index(self.collection, field, field_schema=schema, wait=True)

    def search(self, vector: list[float], filters: dict, limit: int) -> list[dict]:
        if len(vector) != VECTOR_SIZE:
            raise ValueError(f"Qdrant vector must contain {VECTOR_SIZE} values")
        conditions = []
        for key in ("camera_id", "object_type"):
            if filters.get(key):
                conditions.append(FieldCondition(key=key, match=MatchValue(value=filters[key])))
        if filters.get("risk_level"):
            conditions.append(FieldCondition(key="risk.level", match=MatchValue(value=filters["risk_level"])))
        if filters.get("start_at") or filters.get("end_at"):
            conditions.append(FieldCondition(key="occurred_at", range=DatetimeRange(
                gte=filters.get("start_at"), lt=filters.get("end_at")
            )))
        result = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=Filter(must=conditions) if conditions else None,
            limit=limit,
            with_payload=False,
        )
        return [{"event_id": str(point.id), "score": float(point.score)} for point in result.points]
