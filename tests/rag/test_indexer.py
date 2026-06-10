"""SegmentIndex の integration テスト (要 Qdrant + fastembed モデルダウンロード).

初回はモデル (~100MB) のダウンロードが走る. 2 回目以降は HF キャッシュで高速.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from clipmind.rag.embeddings import FastEmbedProvider
from clipmind.rag.fuse import TimelineSegment
from clipmind.rag.indexer import SegmentIndex

pytestmark = pytest.mark.integration

QDRANT_URL = "http://localhost:6333"


@pytest.fixture
async def index() -> SegmentIndex:
    return SegmentIndex(QDRANT_URL, FastEmbedProvider())


async def test_index_and_hybrid_search(index: SegmentIndex) -> None:
    """index → dense / hybrid 検索で意味的に近い segment が上位に来る."""
    vid = uuid4()
    segments = [
        TimelineSegment(
            video_id=vid,
            start_ms=0,
            end_ms=5000,
            transcript="The presenter shows the quarterly revenue results on a slide.",
        ),
        TimelineSegment(
            video_id=vid,
            start_ms=5000,
            end_ms=10000,
            transcript="A cat is playing with a ball of yarn on the floor.",
        ),
        TimelineSegment(
            video_id=vid,
            start_ms=10000,
            end_ms=15000,
            transcript="The team discusses the marketing strategy for next year.",
        ),
    ]
    try:
        count = await index.index_segments(segments)
        assert count == 3

        # dense: 意味検索
        dense_hits = await index.search_dense(
            "financial results presentation", top_k=2, video_id=str(vid)
        )
        assert len(dense_hits) >= 1
        assert "revenue" in dense_hits[0].text

        # hybrid: キーワード + 意味
        hybrid_hits = await index.search_hybrid("cat playing", top_k=2, video_id=str(vid))
        assert len(hybrid_hits) >= 1
        assert "cat" in hybrid_hits[0].text

        # video_id フィルタ: 他動画は混ざらない
        other_hits = await index.search_hybrid("cat", top_k=5, video_id=str(uuid4()))
        assert other_hits == []
    finally:
        await index.delete_video(str(vid))
        await index.close()


async def test_reindex_overwrites_same_window(index: SegmentIndex) -> None:
    """同じ (video_id, start_ms) の再 index は上書きされ、件数が増えない."""
    vid = uuid4()
    seg = TimelineSegment(video_id=vid, start_ms=0, end_ms=5000, transcript="first version")
    try:
        await index.index_segments([seg])
        seg2 = TimelineSegment(video_id=vid, start_ms=0, end_ms=5000, transcript="updated version")
        await index.index_segments([seg2])

        hits = await index.search_dense("version", top_k=10, video_id=str(vid))
        assert len(hits) == 1
        assert hits[0].text == "updated version"
    finally:
        await index.delete_video(str(vid))
        await index.close()
