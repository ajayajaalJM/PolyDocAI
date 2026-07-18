from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../local.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PolyDoc AI"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    cors_origins: list[str] = ["http://localhost:2727"]

    storage_root: str = "../storage"
    max_upload_size_mb: int = 50
    allowed_mime_types: list[str] = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
    ]

    ollama_base_url: str = "http://localhost:11434"
    openai_compatible_base_url: str = "http://localhost:1234/v1"
    default_translator: str = "ollama"
    default_ollama_model: str = "llama3.2"
    default_openai_model: str = "local-model"

    ocr_lang: str = "en"
    ocr_dpi: int = 300
    layout_confidence: float = 0.35
    layout_imgsz: int = 1024

    pipeline_max_concurrency: int = 2
    pipeline_cache_enabled: bool = True
    cache_version: str = "v2"
    vision_provider: str = "heuristic"
    ollama_vision_model: str = "llama3.2-vision"

    source_language: str = "en"
    target_language: str = "es"


@lru_cache
def get_settings() -> Settings:
    return Settings()
