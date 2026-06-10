"""QueryToolbox / build_tools のテスト.

- unit: hybrid_search (fake SegmentIndex) と build_tools のスキーマ
- integration: DB 系ツール (filter_by_time / filter_by_object / get_video_metadata)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlmodel import col

from clipmind.agents.tools import QueryToolbox, build_tools
from clipmind.rag.indexer import SearchHit
from clipmind.storage.object_store import LocalFSObjectStore


class FakeSegmentIndex:
    """search_hybrid だけ返す duck-typed fake."""

    async def search_hybrid(
        self, query: str, *, top_k: int = 5, video_id: str | None = None, prefetch_k: int = 20
    ) -> list[SearchHit]:
        return [
            SearchHit(
                video_id=video_id or "v",
                start_ms=0,
                end_ms=5000,
                text=f"segment about {query}",
                score=0.9,
            )
        ][:top_k]


def _toolbox(tmp_path: Path, session_maker: Any = None) -> QueryToolbox:
    return QueryToolbox(
        segment_index=FakeSegmentIndex(),  # type: ignore[arg-type]
        session_maker=session_maker,
        object_store=LocalFSObjectStore(base_dir=tmp_path / "objects"),
    )


async def test_hybrid_search_tool_returns_dicts(tmp_path: Path) -> None:
    toolbox = _toolbox(tmp_path)
    result = await toolbox.hybrid_search("q3 results", top_k=3, video_id="vid-1")
    assert result == [
        {
            "video_id": "vid-1",
            "start_ms": 0,
            "end_ms": 5000,
            "text": "segment about q3 results",
            "score": 0.9,
        }
    ]


def test_build_tools_exposes_five_tools(tmp_path: Path) -> None:
    """architecture.md §4.2 の Tool が揃っている (summarize は Agent 内製)."""
    tools = build_tools(_toolbox(tmp_path))
    names = {t.name for t in tools}
    assert names == {
        "hybrid_search",
        "filter_by_time",
        "filter_by_object",
        "get_frame_image",
        "get_video_metadata",
    }
    # 各 Tool に description があり LLM がツール選択できる
    assert all(t.description for t in tools)


@pytest.mark.integration
async def test_db_tools_roundtrip(tmp_path: Path) -> None:
    """filter_by_time / filter_by_object / get_video_metadata が実 DB で動く."""
    from clipmind.storage.db import get_session_maker
    from clipmind.storage.models import Detection, TranscriptSegment, Video

    maker = get_session_maker()
    vid = uuid4()
    async with maker() as session:
        # FK 依存があるので Video を先に flush してから子テーブルを入れる
        session.add(Video(id=vid, sha256=vid.hex, object_store_key="x"))
        await session.flush()
        session.add(
            TranscriptSegment(video_id=vid, start_ms=1000, end_ms=4000, text="hello inside")
        )
        session.add(TranscriptSegment(video_id=vid, start_ms=9000, end_ms=12000, text="outside"))
        session.add(
            Detection(
                video_id=vid,
                frame_index=2,
                label="person",
                confidence=0.8,
                bbox_x1=0,
                bbox_y1=0,
                bbox_x2=5,
                bbox_y2=5,
            )
        )
        await session.commit()

    toolbox = QueryToolbox(
        segment_index=FakeSegmentIndex(),  # type: ignore[arg-type]
        session_maker=maker,
        object_store=LocalFSObjectStore(base_dir=tmp_path / "objects"),
    )
    try:
        segs = await toolbox.filter_by_time(str(vid), 0, 5000)
        assert [s["text"] for s in segs] == ["hello inside"]

        dets = await toolbox.filter_by_object(str(vid), "person", min_confidence=0.5)
        assert len(dets) == 1
        assert dets[0]["label"] == "person"

        meta = await toolbox.get_video_metadata(str(vid))
        assert meta["video_id"] == str(vid)
        assert meta["status"] == "queued"
    finally:
        async with maker() as session:
            await session.execute(delete(Video).where(col(Video.id) == vid))
            await session.commit()
