"""`GET /health` エンドポイント.

api-spec.md §2.11 に従う. Phase 1 では Postgres 接続確認のみ実装、
他は `"skipped"` を返す.
"""

from __future__ import annotations

from fastapi import APIRouter

from clipmind.api.schemas import DepsStatus, HealthResponse
from clipmind.storage.health import postgres_ping

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """サービス稼働状況. Phase 1 は Postgres のみ実体チェック."""
    pg_ok = await postgres_ping()
    deps = DepsStatus(
        postgres="ok" if pg_ok else "error",
        redis="skipped",
        qdrant="skipped",
        anthropic="skipped",
    )
    status = "healthy" if pg_ok else "degraded"
    return HealthResponse(status=status, deps=deps)
