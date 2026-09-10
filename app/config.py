"""
Centralized Configuration
Uses pydantic-settings for validated environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):

    # LLM Configuration
    gemini_api_key: str
    primary_model: str = "gemini-3.6-flash"
    fallback_model: str = "gemini-3.6-flash"

    # LangSmith
    langchain_tracing_v2: bool = True
    langsmith_api_key: str = ""
    langsmith_project: str = "production-api"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    rate_limit: str = "20/minute"
    cache_ttl_seconds: int = 300
    max_retries: int = 3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance - loaded once, reused everywhere.
    Singleton class
    """
    return Settings()
