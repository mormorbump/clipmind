"""detect_objects ノード: キーフレームに YOLO 検知をかける.

extract_frames の後段で transcribe 系と並列に実行される (Phase 2 fan-out).
ultralytics が無い環境では errors に追記して継続 (部分失敗で Ingest は止めない).
"""

from __future__ import annotations

import asyncio

from clipmind.graph.state import DetectionRecord, IngestState
from clipmind.storage.object_store import ObjectStore


def make_detect_objects_node(  # type: ignore[no-untyped-def]
    object_store: ObjectStore,
    *,
    model_name: str = "yolov8n.pt",
    min_confidence: float = 0.4,
):
    """`object_store` から frame JPEG を読み出して YOLO をかけるノードを返す."""

    async def detect_objects_node(state: IngestState) -> IngestState:
        frames = state.get("frames", [])
        if not frames:
            return {}

        try:
            from clipmind.ingest.detector import detect_objects
        except ImportError as e:
            return {"errors": [f"detect_objects: ultralytics unavailable: {e}"]}

        records: list[DetectionRecord] = []
        try:
            for frame in frames:
                jpeg = await object_store.get(frame["object_store_key"])
                detections = await asyncio.to_thread(
                    detect_objects,
                    jpeg,
                    model_name=model_name,
                    min_confidence=min_confidence,
                )
                records.extend(
                    DetectionRecord(
                        frame_index=frame["index"],
                        label=d.label,
                        confidence=d.confidence,
                        bbox=d.bbox,
                    )
                    for d in detections
                )
        except Exception as e:
            return {"errors": [f"detect_objects: {e}"], "detections": records}

        return {"detections": records}

    return detect_objects_node
