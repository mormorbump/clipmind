"""index ノード: State の transcript/detection/caption を fuse して Qdrant に upsert.

Qdrant が落ちていても Ingest 自体は失敗させない (errors 追記で継続).
"""

from __future__ import annotations

from uuid import UUID

from clipmind.graph.state import IngestState
from clipmind.rag.fuse import fuse_timeline
from clipmind.rag.indexer import SegmentIndex
from clipmind.storage.models import Detection, FrameCaption, TranscriptSegment


def make_index_segments_node(segment_index: SegmentIndex):  # type: ignore[no-untyped-def]
    """SegmentIndex をクロージャに閉じた index ノードを返す."""

    async def index_segments_node(state: IngestState) -> IngestState:
        video_id_str = state.get("video_id")
        if not video_id_str:
            return {"errors": ["index: video_id is empty"]}
        try:
            video_uuid = UUID(video_id_str)
        except ValueError:
            return {"errors": [f"index: invalid video_id: {video_id_str!r}"]}

        frame_timestamps = {f["index"]: f["timestamp_ms"] for f in state.get("frames", [])}

        # fuse_timeline は DB モデルを期待するので State から組み立てる
        transcripts = [
            TranscriptSegment(
                video_id=video_uuid, start_ms=t["start_ms"], end_ms=t["end_ms"], text=t["text"]
            )
            for t in state.get("transcripts", [])
        ]
        detections = [
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
        captions = [
            FrameCaption(
                video_id=video_uuid,
                frame_index=c["frame_index"],
                text=c["text"],
                model=c["model"],
            )
            for c in state.get("captions", [])
        ]

        segments = fuse_timeline(video_uuid, transcripts, detections, captions, frame_timestamps)
        if not segments:
            return {}

        try:
            await segment_index.index_segments(segments)
        except Exception as e:
            return {"errors": [f"index: {e}"]}
        return {}

    return index_segments_node
