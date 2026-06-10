"""store ノード: State の frames / transcripts を Postgres に書き出す.

video_id は state 上では str (UUID の hex) として持ち、ここで UUID に戻して Repo に渡す.
api 層がアップロード時に Video レコードを事前に作っている前提.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clipmind.graph.state import IngestState
from clipmind.storage.models import Detection, Frame, FrameCaption, TranscriptSegment
from clipmind.storage.repositories.video import VideoRepository


def make_store_node(
    session_maker: async_sessionmaker[AsyncSession],
) -> Callable[[IngestState], Awaitable[IngestState]]:
    """`session_maker` をクロージャに閉じた store ノードを返す."""

    async def store_node(state: IngestState) -> IngestState:
        video_id_str = state.get("video_id")
        if not video_id_str:
            return {"errors": ["store: video_id is empty"]}

        try:
            video_uuid = UUID(video_id_str)
        except ValueError:
            return {"errors": [f"store: invalid video_id (not UUID): {video_id_str!r}"]}

        frame_models: list[Frame] = [
            Frame(
                video_id=video_uuid,
                frame_index=f["index"],
                timestamp_ms=f["timestamp_ms"],
                object_store_key=f["object_store_key"],
            )
            for f in state.get("frames", [])
        ]
        seg_models: list[TranscriptSegment] = [
            TranscriptSegment(
                video_id=video_uuid,
                start_ms=s["start_ms"],
                end_ms=s["end_ms"],
                text=s["text"],
            )
            for s in state.get("transcripts", [])
        ]
        detection_models: list[Detection] = [
            Detection(
                video_id=video_uuid,
                frame_index=d["frame_index"],
                label=d["label"],
                confidence=d["confidence"],
                bbox_x1=d["bbox"][0],
                bbox_y1=d["bbox"][1],
                bbox_x2=d["bbox"][2],
                bbox_y2=d["bbox"][3],
            )
            for d in state.get("detections", [])
        ]
        caption_models: list[FrameCaption] = [
            FrameCaption(
                video_id=video_uuid,
                frame_index=c["frame_index"],
                text=c["text"],
                model=c["model"],
            )
            for c in state.get("captions", [])
        ]

        async with session_maker() as session:
            repo = VideoRepository(session)
            if frame_models:
                await repo.add_frames(frame_models)
            if seg_models:
                await repo.add_transcript_segments(seg_models)
            if detection_models:
                session.add_all(detection_models)
                await session.commit()
            if caption_models:
                session.add_all(caption_models)
                await session.commit()
            await repo.mark_completed(video_uuid)

        return {}

    return store_node
