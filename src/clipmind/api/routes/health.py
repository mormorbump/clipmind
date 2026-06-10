"""`GET /health` エンドポイント.

api-spec.md §2.11 に従う. Phase 8 時点: postgres / qdrant / redis を実体チェック、
anthropic はキー未投入のため `"skipped"`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from clipmind.api.deps import get_settings
from clipmind.api.schemas import DepsStatus, HealthResponse
from clipmind.config import Settings
from clipmind.storage.health import postgres_ping, qdrant_ping, redis_ping

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """サービス稼働状況. postgres / qdrant / redis を実体チェック."""
    pg_ok = await postgres_ping()
    qd_ok = await qdrant_ping(settings.qdrant_url)
    rd_ok = await redis_ping(settings.redis_url)
    deps = DepsStatus(
        postgres="ok" if pg_ok else "error",
        redis="ok" if rd_ok else "error",
        qdrant="ok" if qd_ok else "error",
        anthropic="skipped",
    )
    status = "healthy" if (pg_ok and qd_ok and rd_ok) else "degraded"
    return HealthResponse(status=status, deps=deps)
