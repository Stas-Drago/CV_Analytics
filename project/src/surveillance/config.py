import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://surveillance:surveillance@localhost:5432/surveillance"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "surveillance_events_labse_v1"
    qdrant_timeout_seconds: float = 10.0
    embedding_model: str = "sentence-transformers/LaBSE"
    camera_device_index: int = 0
    camera_width: int = 1280
    camera_height: int = 720
    preview_jpeg_quality: int = 80
    preview_interval_seconds: float = 0.2
    model_registry_dir: str = ""
    yolo_model_path: str = "models/yolo26n.pt"
    yolo_model_manifest: str = "models/manifest/yolo26n.json"
    yolo_device: str = "mps"
    yolo_confidence_threshold: float = 0.45
    yolo_classes: str = ""
    tracker_config: str = "src/surveillance/camera/bytetrack.yaml"
    tracker_id_reset_missing_frames: int = 15
    tracker_id_iou_threshold: float = 0.5
    event_min_track_age_seconds: float = 2.0
    event_presence_timeout_seconds: float = 20.0
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5vl:7b"
    ollama_timeout_seconds: float = 90.0
    ollama_num_ctx: int = 4096
    vision_backend: str = "ollama"
    mlx_python_path: str = ".venv-mlx/bin/python"
    mlx_model_path: str = ""
    mlx_max_tokens: int = 160
    vision_prompt_version: str = "visible-facts-ru-v1"
    danger_model_path: str = ""
    danger_model_manifest: str = "models/manifest/danger_mlp.json"
    danger_model_card: str = "models/model_card.md"
    danger_embedding_model: str = "sentence-transformers/LaBSE"
    # Explicitly local-only opt-in for a checksum-verified draft release. It
    # never changes the shadow-only task behaviour of RiskWorker.
    danger_allow_local_draft: bool = False
    analysis_poll_seconds: float = 1.0
    analysis_max_attempts: int = 3
    analysis_lock_key: str = "surveillance:analysis-inference"
    outbox_processing_timeout_seconds: int = 300
    analytics_database_url: str = ""
    postgres_reader_password: str = ""
    query_timezone: str = "Europe/Moscow"
    query_stream_max_length: int = 1000
    query_result_ttl_seconds: int = 120
    query_api_wait_seconds: float = 60.0
    query_vector_top_k: int = 10
    query_vector_max_top_k: int = 20
    query_vector_timeout_seconds: float = 3.0
    query_sql_timeout_ms: int = 3000
    query_list_limit: int = 100
    query_max_range_days: int = 31
    query_ollama_intent_timeout_seconds: float = 25.0
    query_ollama_summary_timeout_seconds: float = 30.0
    auth_session_cookie_name: str = "surveillance_session"
    auth_session_hours: int = 4
    auth_idle_minutes: int = 15
    auth_cookie_secure: bool = False


@lru_cache
def settings() -> Settings:
    return Settings(_env_file=os.getenv("SETTINGS_ENV_FILE", ".env"))
