"""
orchestrator_core/config.py

Lazy settings configuration using pydantic-settings.
Settings are loaded on demand and cached, avoiding any import-time side effects
or reliance on global mutable singletons.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings read from environment variables and .env file."""

    database_path: str = "database/orchestrator.db"
    chroma_db_dir: str = "chroma_db"
    groq_api_key: Optional[str] = None
    router_model: str = "llama-3.3-70b-versatile"
    router_confidence_threshold: float = 0.6
    auth_token: Optional[str] = None
    environment: str = "development"
    app_version: str = "2.0.0-alpha"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance. Safe to use as a FastAPI dependency."""
    return Settings()
