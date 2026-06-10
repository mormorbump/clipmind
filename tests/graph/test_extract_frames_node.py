"""extract_frames ノードのテスト."""

from __future__ import annotations

from pathlib import Path

from clipmind.graph.nodes.extract_frames import make_extract_frames_node
from clipmind.storage.object_store import LocalFSObjectStore


async def test_extract_frames_node_writes_to_object_store(
    synthetic_video: Path, tmp_path: Path
) -> None:
    """ノード実行で ObjectStore に画像が保存され、State に frames が追記される."""
    store = LocalFSObjectStore(base_dir=tmp_path / "objects")
    node = make_extract_frames_node(store)

    new_state = await node(
        {"video_id": "vid_test", "source": "local", "video_path": str(synthetic_video)}
    )

    frames = new_state["frames"]
    assert len(frames) >= 2
    for f in frames:
        path = (tmp_path / "objects" / f["object_store_key"]).resolve()
        assert path.is_file()
        assert path.stat().st_size > 0
