import hashlib
import unicodedata

from fastapi import APIRouter, HTTPException

from surveillance.config import settings
from surveillance.events.models import QueryRequest
from surveillance.query.broker import QueryTimeoutError, QueryUnavailableError, RedisQueryBroker
from surveillance.storage.postgres import PostgresEventRepository

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post("")
def query(item: QueryRequest) -> dict:
    cfg = settings()
    normalized = unicodedata.normalize("NFKC", item.request).strip().casefold()
    request_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    try:
        result = RedisQueryBroker(cfg.redis_url, cfg.query_result_ttl_seconds, cfg.query_stream_max_length).submit_and_wait(
            item.request, cfg.query_api_wait_seconds
        )
    except QueryTimeoutError as error:
        raise HTTPException(status_code=504, detail={"code": "query_timeout"}) from error
    except QueryUnavailableError as error:
        raise HTTPException(status_code=503, detail={"code": "query_unavailable"}) from error
    route, meta = result.get("route", "vector"), result.get("meta", {})
    operation = meta.get("operation")
    error_code = result.get("error_code")
    try:
        PostgresEventRepository(cfg.database_url).write_query_audit(
            request_hash=request_hash, route=route, operation=operation, filters=meta.get("filters", {}),
            outcome="error" if error_code else "completed", latency_ms=int(meta.get("duration_ms", 0)),
            result_count=len(result.get("evidence", [])), error_code=error_code,
        )
    except Exception:
        # Audit failure must not disclose internals or alter a read result.
        pass
    if route == "clarification" or error_code == "clarification_required":
        raise HTTPException(status_code=422, detail={"code": "clarification_required",
            "missing_fields": result.get("missing_fields", [])})
    if error_code:
        raise HTTPException(status_code=503, detail={"code": error_code})
    return result
