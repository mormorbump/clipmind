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
