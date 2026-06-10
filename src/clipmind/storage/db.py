"""非同期 SQLAlchemy エンジン + セッション factory.

ADR-0008 に従い、SQLModel + SQLAlchemy 2.x async + asyncpg を採用.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from clipmind.api.deps import get_settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """プロセス内シングルトン engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """セッション factory (expire_on_commit=False)."""
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends 用の async generator."""
    maker = get_session_maker()
    async with maker() as session:
        yield session


async def dispose_engine() -> None:
    """テストやシャットダウン時のクリーンアップ."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None
