from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    redis_url: str
    qdrant_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "surveillance-media"
    ollama_host: str
    ollama_model: str
    embedding_model: str = "sentence-transformers/LaBSE"
    risk_model_path: str = "/models/danger_mlp.pt"
    risk_model_version: str = "untrained"
    camera_1_url: str = ""
    camera_2_url: str = ""
    camera_3_url: str = ""
    camera_4_url: str = ""

    @property
    def cameras(self) -> dict[str, str]:
        return {f"camera-{i}": url for i, url in enumerate(
            [self.camera_1_url, self.camera_2_url, self.camera_3_url, self.camera_4_url], 1
        ) if url}


@lru_cache
def settings() -> Settings:
    return Settings()
