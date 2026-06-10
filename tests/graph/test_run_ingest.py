"""LangGraph 通しテスト (integration).

合成動画 (ffmpeg 不要、OpenCV だけで生成) で graph 全体を invoke する.
ffmpeg / faster-whisper が未インストールでも frames は Postgres に保存される
(extract_audio がエラーになり transcribe は skip パスを通る).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlmodel import col

from clipmind.graph.runner import run_ingest
from clipmind.storage.db import get_session_maker
from clipmind.storage.models import Video
from clipmind.storage.object_store import LocalFSObjectStore
from clipmind.storage.repositories.video import VideoRepository

pytestmark = pytest.mark.integration


async def test_run_ingest_persists_frames_to_postgres(
    synthetic_video: Path, tmp_path: Path
) -> None:
    """合成動画を ingest. frames が Postgres に保存される (transcripts は環境依存)."""
    maker = get_session_maker()
    video_uuid = uuid4()
    sha = video_uuid.hex  # 一意な dummy sha

    async with maker() as session:
        session.add(
            Video(id=video_uuid, sha256=sha, object_store_key=f"videos/{video_uuid.hex}/x.mp4")
        )
        await session.commit()

    object_store = LocalFSObjectStore(base_dir=tmp_path / "objects")
    try:
        await run_ingest(
            video_id=video_uuid.hex,
            video_path=synthetic_video,
            object_store=object_store,
            audio_dir=tmp_path / "audio",
            checkpoint_db_path=tmp_path / "ckpt.db",
            session_maker=maker,
        )

        async with maker() as session:
            repo = VideoRepository(session)
            assert await repo.count_frames(video_uuid) >= 2
    finally:
        async with maker() as session:
            await session.execute(delete(Video).where(col(Video.id) == video_uuid))
            await session.commit()
