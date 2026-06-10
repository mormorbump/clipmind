"""FastAPI アプリケーション entry point.

`uv run uvicorn clipmind.api.main:app` でローカル起動.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from clipmind.api.deps import get_settings
from clipmind.api.routes import ask, health, progress_ws, query, videos


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """起動時にデータディレクトリを作成し、終了時には特に何もしない."""
    settings = get_settings()
    settings.object_store_dir.mkdir(parents=True, exist_ok=True)
    settings.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    """FastAPI app factory."""
    app = FastAPI(
        title="ClipMind API",
        version="0.1.0",
        description="動画コンテンツを対話型で検索・質問できるマルチエージェント RAG.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(videos.router)
    app.include_router(query.router)
    app.include_router(ask.router)
    app.include_router(progress_ws.router)

    # Prometheus メトリクス (M8-2): /metrics で exposition format を公開
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["metrics"])

    # Object Store 配下を公開プレフィックス (既定 /static, 環境により /media 等) で配信
    settings = get_settings()
    static_dir = settings.object_store_dir
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.object_store_url_prefix,
        StaticFiles(directory=Path(static_dir)),
        name="object-store",
    )
    return app


app = create_app()
