"""環境変数ベースの設定.

Pydantic Settings で .env / 環境変数を読み込み、型安全に提供する.
"""

from pathlib import Path

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

    # 観測性
    langsmith_api_key: str = Field(default="", description="LangSmith API key")
    langsmith_tracing: bool = Field(default=False, description="Enable LangSmith tracing")
    langsmith_project: str = Field(default="clipmind", description="LangSmith project name")

    # Ingest チューニング (Phase 2)
    whisper_model_size: str = Field(default="base", description="faster-whisper モデルサイズ")
    enable_detection: bool = Field(default=True, description="YOLO 物体検知を有効化")
    max_caption_frames: int = Field(
        default=20, description="キャプション対象フレーム数上限 (コスト制御)"
    )
    caption_model_openai: str = Field(default="gpt-4o-mini", description="キャプション主モデル")
    caption_model_anthropic: str = Field(
        default="claude-haiku-4-5", description="キャプション フォールバックモデル"
    )

    # RAG (Phase 3)
    enable_indexing: bool = Field(default=True, description="Qdrant への segment インデックス")
    enable_rerank: bool = Field(
        default=False, description="CrossEncoder 再ランク (モデルダウンロードが走るため既定 off)"
    )

    # 運用 (Phase 8)
    enable_async_ingest: bool = Field(
        default=False,
        description="True なら Ingest を RQ ワーカーに退避 (要 redis + rq worker プロセス)",
    )

    # Phase 1: ローカル開発の永続データ配置先（.gitignore 済み）
    data_dir: Path = Field(
        default=Path(".data"), description="ローカル開発で使う永続データの基準ディレクトリ"
    )
    object_store_subdir: str = Field(
        default="objects", description="data_dir 配下の Object Store サブディレクトリ"
    )
    checkpoint_db_subpath: str = Field(
        default="checkpoints/ingest.db",
        description="data_dir 配下の LangGraph SQLite Checkpointer ファイル",
    )

    @property
    def object_store_dir(self) -> Path:
        """LocalFSObjectStore のルートディレクトリ."""
        return self.data_dir / self.object_store_subdir

    @property
    def checkpoint_db_path(self) -> Path:
        """LangGraph SQLite Checkpointer ファイルパス."""
        return self.data_dir / self.checkpoint_db_subpath


def get_settings() -> Settings:
    """Settings を返す（テストで dependency override しやすいよう関数化）."""
    return Settings()
