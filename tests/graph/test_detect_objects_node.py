"""detect_objects ノードのテスト.

YOLO 実推論 (yolov8n ダウンロード + torch) は integration マーカー.
unit ではフレーム無しの早期 return だけ確認.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clipmind.graph.nodes.detect_objects import make_detect_objects_node
from clipmind.graph.state import Frame
from clipmind.storage.object_store import LocalFSObjectStore


async def test_detect_objects_no_frames_returns_empty(tmp_path: Path) -> None:
    """frames が空なら何もしない."""
    store = LocalFSObjectStore(base_dir=tmp_path / "objects")
    node = make_detect_objects_node(store)
    assert await node({"video_id": "vid", "frames": []}) == {}


@pytest.mark.integration
async def test_detect_objects_runs_yolo_on_synthetic_frame(tmp_path: Path) -> None:
    """単色フレームに YOLO をかける (検知 0 件で正常終了するのが期待値)."""
    import cv2
    import numpy as np

    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[:, :, 2] = 200
    ok, buf = cv2.imencode(".jpg", img)
    assert ok

    store = LocalFSObjectStore(base_dir=tmp_path / "objects")
    key = "frames/vid/f_000000.jpg"
    await store.put(key, buf.tobytes())

    node = make_detect_objects_node(store)
    result = await node(
        {
            "video_id": "vid",
            "frames": [Frame(index=0, timestamp_ms=0, object_store_key=key)],
        }
    )
    # 単色 64x64 から物体は出ないはず. エラーが無く detections キーが返ることが大事.
    assert "errors" not in result or not result["errors"], result.get("errors")
    assert result.get("detections", []) == []
