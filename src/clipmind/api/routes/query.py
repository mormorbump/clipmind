"""`POST /api/v1/videos/{video_id}/query` エンドポイント (M3-2 / M3-3).

Phase 3 では「関連セグメント返却」まで (api-spec.md §2.7 の answer 生成は Phase 5 の Agent で).
mode=dense | hybrid を選択可能. hybrid がデフォルト.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from clipmind.api.deps import get_segment_index
from clipmind.rag.indexer import SegmentIndex

router = APIRouter(prefix="/api/v1/videos", tags=["query"])


class QueryRequest(BaseModel):
    """検索リクエスト."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=50)
    mode: Literal["dense", "hybrid"] = "hybrid"


class SegmentHit(BaseModel):
    """検索結果 1 件."""

    model_config = ConfigDict(extra="forbid")

    video_id: str
    start_ms: int
    end_ms: int
    text: str
    score: float


class QueryResponse(BaseModel):
    """検索レスポンス."""

    model_config = ConfigDict(extra="forbid")

    query: str
    mode: Literal["dense", "hybrid"]
    hits: list[SegmentHit]


@router.post("/{video_id}/query", response_model=QueryResponse)
async def query_video(
    video_id: str,
    body: QueryRequest,
    segment_index: Annotated[SegmentIndex, Depends(get_segment_index)],
) -> QueryResponse:
    """1 動画に対する自然言語検索. 関連セグメントを返す."""
    try:
        if body.mode == "dense":
            hits = await segment_index.search_dense(body.query, top_k=body.top_k, video_id=video_id)
        else:
            hits = await segment_index.search_hybrid(
                body.query, top_k=body.top_k, video_id=video_id
            )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"search backend unavailable: {e}") from e

    return QueryResponse(
        query=body.query,
        mode=body.mode,
        hits=[
            SegmentHit(
                video_id=h.video_id,
                start_ms=h.start_ms,
                end_ms=h.end_ms,
                text=h.text,
                score=h.score,
            )
            for h in hits
        ],
    )
