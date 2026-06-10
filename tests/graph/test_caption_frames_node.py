"""caption_frames ノードのテスト (FakeCaptioner、API キー不要)."""

from __future__ import annotations

from pathlib import Path

from clipmind.graph.nodes.caption_frames import make_caption_frames_node
from clipmind.graph.state import Frame
from clipmind.llm.captioner import CaptionResult, NullCaptioner
from clipmind.storage.object_store import LocalFSObjectStore


class FakeCaptioner:
    async def caption(self, image_jpeg: bytes) -> CaptionResult | None:
        return CaptionResult(text="a red square", model="fake/model")


async def _store_with_frames(tmp_path: Path) -> tuple[LocalFSObjectStore, list[Frame]]:
    store = LocalFSObjectStore(base_dir=tmp_path / "objects")
    frames: list[Frame] = []
    for i in range(3):
        key = f"frames/vid/f_{i:06d}.jpg"
        await store.put(key, b"\xff\xd8fakejpeg")
        frames.append(Frame(index=i, timestamp_ms=i * 1000, object_store_key=key))
    return store, frames


async def test_caption_frames_with_fake_captioner(tmp_path: Path) -> None:
    """FakeCaptioner で全フレームにキャプションが付く."""
    store, frames = await _store_with_frames(tmp_path)
    node = make_caption_frames_node(store, FakeCaptioner())

    result = await node({"video_id": "vid", "frames": frames})
    captions = result["captions"]
    assert len(captions) == 3
    assert all(c["text"] == "a red square" for c in captions)


async def test_caption_frames_null_captioner_skips(tmp_path: Path) -> None:
    """NullCaptioner (キー無し) はキャプションを生成せず空で返す."""
    store, frames = await _store_with_frames(tmp_path)
    node = make_caption_frames_node(store, NullCaptioner())

    result = await node({"video_id": "vid", "frames": frames})
    assert result == {}


async def test_caption_frames_respects_max_frames(tmp_path: Path) -> None:
    """max_frames でコスト制御."""
    store, frames = await _store_with_frames(tmp_path)
    node = make_caption_frames_node(store, FakeCaptioner(), max_frames=1)

    result = await node({"video_id": "vid", "frames": frames})
    assert len(result["captions"]) == 1
