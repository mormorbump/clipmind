"""extract_frames ノード: 動画からキーフレームを抽出して ObjectStore に保存.

cv2 は同期ライブラリなので `asyncio.to_thread` で blocking を逃がす.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from clipmind.graph.state import Frame, IngestState
from clipmind.ingest.frames import extract_keyframes
from clipmind.storage.object_store import ObjectStore


def make_extract_frames_node(object_store: ObjectStore):  # type: ignore[no-untyped-def]
    """`object_store` をクロージャに閉じたノード関数を返す.

    LangGraph のノードは State だけ受け取る形にしたいので closure 化.
    """

    async def extract_frames_node(state: IngestState) -> IngestState:
        video_path = state.get("video_path")
        if not video_path:
            return {"errors": ["extract_frames: video_path is empty"]}

        video_id = state.get("video_id", "unknown")

        extracted = await asyncio.to_thread(extract_keyframes, Path(video_path))

        frames: list[Frame] = []
        for f in extracted:
            key = f"frames/{video_id}/f_{f.index:06d}.jpg"
            await object_store.put(key, f.jpeg_bytes)
            frames.append(Frame(index=f.index, timestamp_ms=f.timestamp_ms, object_store_key=key))
        return {"frames": frames}

    return extract_frames_node
