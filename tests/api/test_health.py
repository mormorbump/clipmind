"""`GET /health` の最小テスト.

unit テストでは ping 関数を monkeypatch で握りつぶし、外部サービスに触らない.
実 ping は integration テストで検証する.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from clipmind.api.main import create_app


async def _ok(*_a: object, **_kw: object) -> bool:
    return True


async def _bad(*_a: object, **_kw: object) -> bool:
    return False


@pytest.mark.asyncio
async def test_health_returns_healthy_when_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """postgres / qdrant / redis すべて成功なら status='healthy'."""
    monkeypatch.setattr("clipmind.api.routes.health.postgres_ping", _ok)
    monkeypatch.setattr("clipmind.api.routes.health.qdrant_ping", _ok)
    monkeypatch.setattr("clipmind.api.routes.health.redis_ping", _ok)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["deps"]["postgres"] == "ok"
    assert body["deps"]["qdrant"] == "ok"
    assert body["deps"]["redis"] == "ok"
    assert set(body["deps"].keys()) == {"postgres", "redis", "qdrant", "anthropic"}


@pytest.mark.asyncio
async def test_health_returns_degraded_when_postgres_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """postgres_ping が失敗なら status='degraded'."""
    monkeypatch.setattr("clipmind.api.routes.health.postgres_ping", _bad)
    monkeypatch.setattr("clipmind.api.routes.health.qdrant_ping", _ok)
    monkeypatch.setattr("clipmind.api.routes.health.redis_ping", _ok)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["deps"]["postgres"] == "error"
    assert body["deps"]["qdrant"] == "ok"
