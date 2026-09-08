import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_url: str = os.getenv("DB_URL", "sqlite:///./triage.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_key: str = os.getenv("QUEUE_KEY", "triage:pending")
    api_token: str = os.getenv("API_TOKEN", "dev-token")
    llm_endpoint: str = os.getenv("LLM_ENDPOINT", "")


settings = Settings()
