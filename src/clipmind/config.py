"""環境変数ベースの設定。

Pydantic Settings で .env / 環境変数を読み込み、型安全に提供する。
Phase 0 では雛形のみ。Phase 1 以降でフィールドを追加する。
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ClipMind 全体の設定."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM プロバイダ（Phase 2 で本格利用）
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    openai_api_key: str = Field(default="", description="OpenAI API key")

    # データストア
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant endpoint")
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis endpoint")
    database_url: str = Field(
        default="postgresql+asyncpg://clipmind:clipmind@localhost:5432/clipmind",
        description="Postgres async URL",
    )

    # 観測性（任意）
    langsmith_api_key: str = Field(default="", description="LangSmith API key")
    langsmith_tracing: bool = Field(default=False, description="Enable LangSmith tracing")
    langsmith_project: str = Field(default="clipmind", description="LangSmith project name")


def get_settings() -> Settings:
    """Settings を返す（テストで dependency override しやすいよう関数化）."""
    return Settings()
