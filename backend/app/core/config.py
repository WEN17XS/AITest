from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中读取环境变量，方便本地、Docker 和 CI 使用同一套配置。"""

    app_name: str = "AITestHub"
    app_env: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://aitest:aitest@localhost:5433/aitesthub"
    redis_url: str = "redis://localhost:6380/0"
    webhook_secret: str = "change-me"
    auth_secret: str = "please-change-this-auth-secret"
    access_token_expire_minutes: int = 60 * 24

    llm_provider: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
