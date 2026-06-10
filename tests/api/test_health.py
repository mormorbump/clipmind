"""`GET /health` の最小テスト.

unit テストでは `postgres_ping` を monkeypatch で握りつぶし、DB に触らない.
実 Postgres ping は tests/storage/test_video_repo.py で検証する.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from clipmind.api.main import create_app


@pytest.mark.asyncio
async def test_health_returns_healthy_when_postgres_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """postgres_ping が成功なら status='healthy'."""

    async def _ok() -> bool:
        return True

    monkeypatch.setattr("clipmind.api.routes.health.postgres_ping", _ok)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["deps"]["postgres"] == "ok"
    assert set(body["deps"].keys()) == {"postgres", "redis", "qdrant", "anthropic"}


@pytest.mark.asyncio
async def test_health_returns_degraded_when_postgres_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """postgres_ping が失敗なら status='degraded'."""

    async def _bad() -> bool:
        return False

    monkeypatch.setattr("clipmind.api.routes.health.postgres_ping", _bad)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["deps"]["postgres"] == "error"
