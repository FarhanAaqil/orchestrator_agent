"""
orchestrator_core/config.py

Lazy settings configuration using pydantic-settings.
Settings are loaded on demand and cached, avoiding any import-time side effects
or reliance on global mutable singletons.
"""

from functools import lru_cache
from typing import Optional
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings read from environment variables and .env file."""

    database_path: str = "database/orchestrator.db"
    chroma_db_dir: str = "chroma_db"
    groq_api_key: Optional[str] = None
    router_model: str = "openai/gpt-oss-120b"
    router_confidence_threshold: float = 0.6
    auth_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("auth_token", "api_bearer_token"),
    )
    environment: str = "development"
    app_version: str = "1.0.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        import os
        if os.path.exists("/app/data") and self.database_path == "database/orchestrator.db":
            self.database_path = "/app/data/orchestrator.db"
        if os.path.exists("/app/data") and self.chroma_db_dir == "chroma_db":
            self.chroma_db_dir = "/app/data/chroma_db"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance. Safe to use as a FastAPI dependency."""
    return Settings()
