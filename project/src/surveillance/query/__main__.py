import argparse

from surveillance.analysis.embeddings import LabseEmbedder
from surveillance.config import settings
from surveillance.query.analytics import ReaderAnalyticsRepository
from surveillance.query.broker import RedisQueryBroker
from surveillance.query.intent import OllamaQueryClient
from surveillance.query.semantic_search import SemanticSearch
from surveillance.query.worker import QueryWorker
from surveillance.storage.qdrant import QdrantEventIndex
from surveillance.workers.pipeline import InferenceGate


def build_worker() -> QueryWorker:
    cfg = settings()
    broker = RedisQueryBroker(cfg.redis_url, cfg.query_result_ttl_seconds, cfg.query_stream_max_length)
    analytics = ReaderAnalyticsRepository(cfg.analytics_database_url, cfg.query_sql_timeout_ms)
    index = QdrantEventIndex(cfg.qdrant_url, cfg.qdrant_collection, cfg.query_vector_timeout_seconds)
    semantic = SemanticSearch(index, LabseEmbedder(cfg.embedding_model), analytics,
                              cfg.query_vector_top_k, cfg.query_vector_max_top_k)
    intent = OllamaQueryClient(cfg.ollama_host, cfg.ollama_model, cfg.query_ollama_intent_timeout_seconds,
                               cfg.query_ollama_summary_timeout_seconds)
    return QueryWorker(broker, intent, semantic, analytics,
                       InferenceGate(cfg.redis_url, cfg.analysis_lock_key), cfg.query_timezone,
                       cfg.query_max_range_days, cfg.query_list_limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Host-only query worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ensure-qdrant-indexes", action="store_true")
    args = parser.parse_args()
    cfg = settings()
    if args.ensure_qdrant_indexes:
        QdrantEventIndex(cfg.qdrant_url, cfg.qdrant_collection, cfg.query_vector_timeout_seconds).ensure_query_indexes()
        return
    worker = build_worker()
    if args.once:
        worker.run_once(1)
    else:
        worker.run_forever(cfg.analysis_poll_seconds)


if __name__ == "__main__":
    main()
