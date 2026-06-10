"""評価ランナーの integration テスト (要 Qdrant).

合成 segment を index → 評価 → Recall@5 = 1.0 になることを確認する.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from clipmind.eval.dataset import EvalQuery
from clipmind.eval.runner import run_evaluation
from clipmind.rag.embeddings import FastEmbedProvider
from clipmind.rag.fuse import TimelineSegment
from clipmind.rag.indexer import SegmentIndex

pytestmark = pytest.mark.integration

QDRANT_URL = "http://localhost:6333"


async def test_run_evaluation_computes_metrics() -> None:
    vid = uuid4()
    index = SegmentIndex(QDRANT_URL, FastEmbedProvider())
    segments = [
        TimelineSegment(
            video_id=vid,
            start_ms=0,
            end_ms=5000,
            transcript="The presenter introduces the quarterly revenue results.",
        ),
        TimelineSegment(
            video_id=vid,
            start_ms=5000,
            end_ms=10000,
            transcript="A discussion about the office coffee machine maintenance.",
        ),
    ]
    queries = [
        EvalQuery(
            query="quarterly financial results",
            video_id=str(vid),
            relevant_start_ms=(0,),
        ),
    ]
    try:
        await index.index_segments(segments)
        report = await run_evaluation(index, queries)

        assert report.dataset_size == 1
        modes = {r.mode: r for r in report.results}
        assert set(modes) == {"dense", "hybrid"}
        # 関連 segment は明確に 1 つ → どちらのモードでも上位に来るはず
        assert modes["dense"].recall_at_5 == 1.0
        assert modes["hybrid"].recall_at_5 == 1.0
        assert modes["dense"].mrr_score > 0

        md = report.to_markdown()
        assert "Recall@5" in md
        assert "dense" in md and "hybrid" in md
    finally:
        await index.delete_video(str(vid))
        await index.close()
