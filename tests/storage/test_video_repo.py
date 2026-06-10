"""VideoRepository の integration test (要 Postgres).

ローカル: `docker compose up -d postgres` + `alembic upgrade head` 前提.
CI: services.postgres + alembic upgrade head ステップ.

各テストは作成した Video を最後に DELETE してリークしない.
engine の dispose は session-scoped fixture (conftest) に集約.
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import delete
from sqlmodel import col

from clipmind.storage.db import get_session_maker
from clipmind.storage.models import Frame, Video
from clipmind.storage.repositories.video import VideoRepository

pytestmark = pytest.mark.integration


async def _rand_sha() -> str:
    return secrets.token_hex(32)


async def test_create_and_get_by_sha256() -> None:
    """create → get_by_sha256 で同じレコードが返る."""
    maker = get_session_maker()
    sha = await _rand_sha()
    async with maker() as session:
        repo = VideoRepository(session)
        created = await repo.create(sha256=sha, object_store_key=f"videos/{sha}/original.mp4")
        fetched = await repo.get_by_sha256(sha)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.status == "queued"

        await session.execute(delete(Video).where(col(Video.id) == created.id))
        await session.commit()


async def test_add_frames_and_count() -> None:
    """frames を add_all → count_frames で数が一致."""
    maker = get_session_maker()
    sha = await _rand_sha()
    async with maker() as session:
        repo = VideoRepository(session)
        video = await repo.create(sha256=sha, object_store_key=f"videos/{sha}/original.mp4")
        frames = [
            Frame(
                video_id=video.id,
                frame_index=i,
                timestamp_ms=i * 1000,
                object_store_key=f"frames/{video.id}/f_{i:04d}.jpg",
            )
            for i in range(3)
        ]
        await repo.add_frames(frames)
        assert await repo.count_frames(video.id) == 3

        await session.execute(delete(Video).where(col(Video.id) == video.id))
        await session.commit()
