"""Worker process for vision descriptions and risk scoring; API process never imports it."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from surveillance.config import settings
from surveillance.db import Repository
from surveillance.queue import TaskQueue
from surveillance.workers.risk import RiskScorer
from surveillance.fusion import RiskSignal, fuse
from surveillance.domain import RiskLevel

logger = logging.getLogger(__name__)
COLLECTION = "surveillance_events_v1"


def describe(media_uri: str, ollama_host: str, model: str) -> str:
    # MinIO retrieval is deliberately delegated to the approved media adapter.
    if not media_uri:
        return "No media available for analysis."
    response = httpx.post(f"{ollama_host}/api/chat", json={"model": model, "stream": False,
        "messages": [{"role": "system", "content": "Describe only visible facts. Do not identify people or infer intent."},
                     {"role": "user", "content": "Analyze the approved event image."}]}, timeout=60)
    response.raise_for_status()
    return response.json()["message"]["content"]


def assess_frame(media_uri: str, ollama_host: str, model: str) -> RiskSignal:
    """Direct visual signal. Media adapter supplies the image to Ollama in production."""
    if not media_uri:
        return RiskSignal("vision", RiskLevel.low, 0.0, "no media available")
    prompt = ("Assess only visible immediate safety risk in this frame. Return strict JSON with "
              "level (low|medium|high), probability (0..1), reason. Never identify people or infer intent.")
    response = httpx.post(f"{ollama_host}/api/chat", json={"model": model, "format": "json", "stream": False,
        "messages": [{"role": "user", "content": prompt}]}, timeout=60)
    response.raise_for_status()
    payload = json.loads(response.json()["message"]["content"])
    return RiskSignal("vision", RiskLevel(payload["level"]), float(payload["probability"]), payload["reason"])


def run() -> None:
    config = settings(); repository = Repository(config.database_url); queue = TaskQueue(config.redis_url)
    encoder = SentenceTransformer(config.embedding_model); scorer = RiskScorer(config.risk_model_path, config.embedding_model)
    qdrant = QdrantClient(url=config.qdrant_url)
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(COLLECTION, vectors_config=VectorParams(size=768, distance=Distance.COSINE))
    while True:
        event_id = queue.consume()
        if not event_id:
            continue
        try:
            event = repository.get_event(event_id)
            if not event:
                continue
            with ThreadPoolExecutor(max_workers=2) as executor:
                description_future = executor.submit(describe, event.media_uri, config.ollama_host, config.ollama_model)
                vision_future = executor.submit(assess_frame, event.media_uri, config.ollama_host, config.ollama_model)
                text, vision_signal = description_future.result(), vision_future.result()
            level, probability = scorer.score(text)
            fused = fuse(RiskSignal("text", level, probability, "DangerMLP description score"), vision_signal)
            repository.save_analysis(event_id, text, fused.level, fused.probability,
                                     vision_signal.level, vision_signal.probability, fused.rationale)
            vector = encoder.encode(text).tolist()
            qdrant.upsert(COLLECTION, [PointStruct(id=event_id, vector=vector, payload={
                "event_id": event_id, "camera_id": event.camera_id, "occurred_at": event.occurred_at.isoformat(),
                "object_type": event.object_type, "text": text, "source_uri": event.media_uri,
                "model_version": event.model_version,
            })])
        except Exception:
            logger.exception("Vision task failed for event_id=%s", event_id)
