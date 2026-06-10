"""`GET /metrics` (Prometheus) の最小テスト."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from clipmind.api.main import create_app


@pytest.mark.asyncio
async def test_metrics_exposes_prometheus_format() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 何か 1 リクエスト挟んでカウンタを動かす
        await client.get("/docs")
        resp = await client.get("/metrics")

    assert resp.status_code == 200
    body = resp.text
    assert "http_requests_total" in body or "http_request" in body
