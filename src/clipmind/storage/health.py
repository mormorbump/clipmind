"""ヘルスチェック用の軽量 ping ヘルパ.

`/health` から呼ぶ. ベタな `SELECT 1` だけ. 失敗時は例外を握りつぶし False を返す.
"""

from __future__ import annotations

from sqlalchemy import text

from clipmind.storage.db import get_engine


async def postgres_ping() -> bool:
    """Postgres に SELECT 1 を投げて成功すれば True."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def redis_ping(redis_url: str) -> bool:
    """Redis に PING を投げて成功すれば True."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_url)  # type: ignore[no-untyped-call]
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()
    except Exception:
        return False


async def qdrant_ping(qdrant_url: str) -> bool:
    """Qdrant の collection 一覧 API を叩いて成功すれば True."""
    try:
        from qdrant_client import AsyncQdrantClient

        client = AsyncQdrantClient(url=qdrant_url, timeout=3)
        await client.get_collections()
        await client.close()
        return True
    except Exception:
        return False
