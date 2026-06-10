"""Query Agent に渡す Tool 群 (architecture.md §4.2, M5-1).

Tool の実体ロジックは `QueryToolbox` のメソッドとして実装し、
LangChain `@tool` ラッパーは `build_tools()` で生成する.
こうすることで Tool 単体を LLM なしでテストできる.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select
from sqlmodel import col

from clipmind.rag.indexer import SegmentIndex
from clipmind.storage.models import Detection, Frame, Video

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from clipmind.storage.object_store import ObjectStore


class QueryToolbox:
    """Tool 実体. SegmentIndex / DB / ObjectStore をまとめて持つ."""

    def __init__(
        self,
        segment_index: SegmentIndex,
        session_maker: async_sessionmaker[AsyncSession],
        object_store: ObjectStore,
    ) -> None:
        self.segment_index = segment_index
        self.session_maker = session_maker
        self.object_store = object_store

    async def hybrid_search(
        self, query: str, top_k: int = 5, video_id: str | None = None
    ) -> list[dict[str, Any]]:
        """BM25 + dense のハイブリッド検索."""
        hits = await self.segment_index.search_hybrid(query, top_k=top_k, video_id=video_id)
        return [
            {
                "video_id": h.video_id,
                "start_ms": h.start_ms,
                "end_ms": h.end_ms,
                "text": h.text,
                "score": h.score,
            }
            for h in hits
        ]

    async def filter_by_time(
        self, video_id: str, start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]:
        """時刻窓で transcript segment を絞り込む."""
        from clipmind.storage.models import TranscriptSegment

        async with self.session_maker() as session:
            stmt = (
                select(TranscriptSegment)
                .where(col(TranscriptSegment.video_id) == UUID(video_id))
                .where(col(TranscriptSegment.start_ms) < end_ms)
                .where(col(TranscriptSegment.end_ms) > start_ms)
                .order_by(col(TranscriptSegment.start_ms))
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [{"start_ms": r.start_ms, "end_ms": r.end_ms, "text": r.text} for r in rows]

    async def filter_by_object(
        self, video_id: str, label: str, min_confidence: float = 0.5
    ) -> list[dict[str, Any]]:
        """YOLO 検知ラベルで絞り込む."""
        async with self.session_maker() as session:
            stmt = (
                select(Detection)
                .where(col(Detection.video_id) == UUID(video_id))
                .where(col(Detection.label) == label)
                .where(col(Detection.confidence) >= min_confidence)
                .order_by(col(Detection.frame_index))
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "frame_index": r.frame_index,
                "label": r.label,
                "confidence": r.confidence,
            }
            for r in rows
        ]

    async def get_frame_image(self, video_id: str, timestamp_ms: int) -> dict[str, Any]:
        """指定時刻に最も近いキーフレームの URL を返す (UI 表示用)."""
        async with self.session_maker() as session:
            stmt = (
                select(Frame)
                .where(col(Frame.video_id) == UUID(video_id))
                .order_by(func.abs(col(Frame.timestamp_ms) - timestamp_ms))
                .limit(1)
            )
            frame = (await session.execute(stmt)).scalars().first()
        if frame is None:
            return {"error": "no frames found"}
        return {
            "frame_url": self.object_store.url_for(frame.object_store_key),
            "timestamp_ms": frame.timestamp_ms,
        }

    async def get_video_metadata(self, video_id: str) -> dict[str, Any]:
        """動画の基本情報."""
        async with self.session_maker() as session:
            video = await session.get(Video, UUID(video_id))
        if video is None:
            return {"error": "video not found"}
        return {
            "video_id": str(video.id),
            "status": video.status,
            "duration_seconds": video.duration_seconds,
            "created_at": video.created_at.isoformat(),
        }


def build_tools(toolbox: QueryToolbox) -> list[Any]:
    """QueryToolbox を LangChain Tool に変換する (M5-1).

    summarize_segment は LLM 呼び出しが必要なので Agent 自身の応答に委ねる
    (Tool としては定義しない. ADR-0003 の fuse 要約は Phase 5 では Agent 内製).
    """
    from langchain_core.tools import tool

    @tool
    async def hybrid_search(
        query: str, top_k: int = 5, video_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Search video segments by meaning and keywords. Returns segments with timestamps."""
        return await toolbox.hybrid_search(query, top_k=top_k, video_id=video_id)

    @tool
    async def filter_by_time(video_id: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        """Get transcript segments within a time window of the video."""
        return await toolbox.filter_by_time(video_id, start_ms, end_ms)

    @tool
    async def filter_by_object(
        video_id: str, label: str, min_confidence: float = 0.5
    ) -> list[dict[str, Any]]:
        """Find frames where a specific object (YOLO label like 'person', 'laptop') was detected."""
        return await toolbox.filter_by_object(video_id, label, min_confidence=min_confidence)

    @tool
    async def get_frame_image(video_id: str, timestamp_ms: int) -> dict[str, Any]:
        """Get the keyframe image URL closest to a timestamp, for showing to the user."""
        return await toolbox.get_frame_image(video_id, timestamp_ms)

    @tool
    async def get_video_metadata(video_id: str) -> dict[str, Any]:
        """Get basic metadata (status, duration, created_at) for a video."""
        return await toolbox.get_video_metadata(video_id)

    return [hybrid_search, filter_by_time, filter_by_object, get_frame_image, get_video_metadata]
