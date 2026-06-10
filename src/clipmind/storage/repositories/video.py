"""Video / Frame / TranscriptSegment の async CRUD."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from clipmind.storage.models import Frame, TranscriptSegment, Video


class VideoRepository:
    """Video まわりの最小限の async リポジトリ."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        sha256: str,
        object_store_key: str,
        source_type: str = "local",
        duration_seconds: float | None = None,
    ) -> Video:
        video = Video(
            sha256=sha256,
            object_store_key=object_store_key,
            source_type=source_type,
            duration_seconds=duration_seconds,
        )
        self.session.add(video)
        await self.session.commit()
        await self.session.refresh(video)
        return video

    async def get(self, video_id: UUID) -> Video | None:
        return await self.session.get(Video, video_id)

    async def get_by_sha256(self, sha256: str) -> Video | None:
        stmt = select(Video).where(col(Video.sha256) == sha256)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 50) -> list[Video]:
        stmt = select(Video).order_by(col(Video.created_at).desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def nearest_frame(self, video_id: UUID, timestamp_ms: int) -> Frame | None:
        from sqlalchemy import func

        stmt = (
            select(Frame)
            .where(col(Frame.video_id) == video_id)
            .order_by(func.abs(col(Frame.timestamp_ms) - timestamp_ms))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def mark_completed(self, video_id: UUID) -> None:
        video = await self.get(video_id)
        if video is None:
            return
        video.status = "completed"
        video.completed_at = datetime.utcnow()
        await self.session.commit()

    async def add_frames(self, frames: list[Frame]) -> None:
        self.session.add_all(frames)
        await self.session.commit()

    async def add_transcript_segments(self, segments: list[TranscriptSegment]) -> None:
        self.session.add_all(segments)
        await self.session.commit()

    async def count_frames(self, video_id: UUID) -> int:
        stmt = select(func.count()).select_from(Frame).where(col(Frame.video_id) == video_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def count_transcript_segments(self, video_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(TranscriptSegment)
            .where(col(TranscriptSegment.video_id) == video_id)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
