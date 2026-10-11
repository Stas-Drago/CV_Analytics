from surveillance.query.models import Evidence, QueryFilters


class SemanticSearch:
    def __init__(self, index: object, embedder: object, analytics: object, top_k: int, max_top_k: int) -> None:
        self.index, self.embedder, self.analytics = index, embedder, analytics
        self.top_k, self.max_top_k = top_k, max_top_k

    def search(self, question: str, filters: QueryFilters) -> list[Evidence]:
        limit = min(self.top_k, self.max_top_k, 20)
        payload_filters = filters.model_dump(mode="json", exclude_none=True)
        vector = self.embedder.encode(question)
        return self.analytics.hydrate(self.index.search(vector, payload_filters, limit))
