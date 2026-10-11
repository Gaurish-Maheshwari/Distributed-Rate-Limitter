from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RL_", env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 100
    redis_timeout: float = 0.5          # seconds; keep small so Redis outages fail fast

    key_prefix: str = "rl"
    fail_open: bool = True              # allow traffic if Redis is down (else 503)
    trust_proxy_headers: bool = False   # honour X-Forwarded-For (only behind a trusted proxy!)
    allow_dynamic_overrides: bool = True
    admin_api_key: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
