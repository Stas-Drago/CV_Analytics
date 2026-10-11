import argparse
import logging
import time

from surveillance.analysis.embeddings import LabseEmbedder
from surveillance.analysis.risk import DangerMLPRiskScorer
from surveillance.analysis.vision import MlxVisionClient, OllamaVisionClient
from surveillance.config import settings
from surveillance.storage.postgres import PostgresEventRepository
from surveillance.storage.qdrant import QdrantEventIndex
from surveillance.workers.pipeline import InferenceGate, QdrantWorker, RiskWorker, VisionWorker
from surveillance.ml.risk_policy import MAPPING_VERSION, THRESHOLD_POLICY_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description="Host-only analysis and Qdrant indexing workers")
    parser.add_argument("kind", choices=("vision", "risk", "qdrant"))
    parser.add_argument("--backfill", action="store_true",
                        help="schedule eligible existing events for the selected worker before polling")
    parser.add_argument("--requeue-dead", action="store_true",
                        help="return dead Qdrant jobs to pending before polling")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    config = settings()
    repository = PostgresEventRepository(config.database_url)
    gate = InferenceGate(config.redis_url, config.analysis_lock_key)
    if args.kind not in {"risk", "qdrant"} and args.backfill:
        parser.error("--backfill requires the risk or qdrant worker")
    if args.kind != "qdrant" and args.requeue_dead:
        parser.error("--requeue-dead requires the qdrant worker")
    if args.kind == "vision":
        if config.vision_backend == "mlx":
            client = MlxVisionClient(config.mlx_python_path, config.mlx_model_path,
                                     config.ollama_timeout_seconds, config.mlx_max_tokens,
                                     config.vision_prompt_version)
        elif config.vision_backend == "ollama":
            client = OllamaVisionClient(config.ollama_host, config.ollama_model,
                                        config.ollama_timeout_seconds, config.ollama_num_ctx,
                                        config.vision_prompt_version)
        else:
            raise ValueError("VISION_BACKEND must be 'mlx' or 'ollama'")
        worker = VisionWorker(repository, client, gate, config.analysis_max_attempts)
    elif args.kind == "risk":
        scorer = DangerMLPRiskScorer(config.danger_model_path, config.danger_model_manifest,
                                    config.danger_embedding_model, config.danger_model_card)
        approved = repository.is_approved_model_release(scorer.model_version, scorer.model_checksum,
                                                        MAPPING_VERSION, THRESHOLD_POLICY_VERSION)
        if not approved and not config.danger_allow_local_draft:
            raise RuntimeError("DangerMLP release is not approved for shadow mode")
        if not approved:
            logging.warning("Running checksum-verified DangerMLP draft in local shadow mode; no autonomous actions are enabled")
        if args.backfill:
            logging.info("Scheduled %s described events for DangerMLP backfill",
                         repository.schedule_risk_backfill(scorer.model_version))
        worker = RiskWorker(repository, scorer, gate, config.analysis_max_attempts)
    else:
        if args.backfill:
            logging.info("Scheduled %s described events for Qdrant backfill", repository.schedule_qdrant_backfill())
        if args.requeue_dead:
            logging.info("Requeued %s dead Qdrant jobs", repository.requeue_dead_qdrant_jobs())
        worker = QdrantWorker(
            repository,
            QdrantEventIndex(config.qdrant_url, config.qdrant_collection, config.qdrant_timeout_seconds),
            LabseEmbedder(config.embedding_model),
            gate,
            config.analysis_max_attempts,
            config.embedding_model,
            config.outbox_processing_timeout_seconds,
        )
    while True:
        if not worker.run_once():
            time.sleep(config.analysis_poll_seconds)


if __name__ == "__main__":
    main()
