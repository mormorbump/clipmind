"""`POST /api/v1/videos/{video_id}/ask` エンドポイント (M5-2).

Query Agent に 1 問 1 答で質問する. LLM キーが無い環境では 503.
WebSocket ストリーミング (M5-3) は Phase 8 の非同期化と同時に実装する.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from clipmind.agents.query_agent import AgentUnavailableError, ask, build_query_agent
from clipmind.agents.tools import QueryToolbox
from clipmind.api.deps import get_object_store, get_segment_index, get_settings

router = APIRouter(prefix="/api/v1/videos", tags=["ask"])


class AskRequest(BaseModel):
    """質問リクエスト."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class AskResponse(BaseModel):
    """Agent の回答."""

    model_config = ConfigDict(extra="forbid")

    video_id: str
    question: str
    answer: str


@lru_cache(maxsize=1)
def get_query_agent() -> Any:
    """Query Agent シングルトン. キーが無ければ AgentUnavailableError."""
    from clipmind.storage.db import get_session_maker

    settings = get_settings()
    toolbox = QueryToolbox(
        segment_index=get_segment_index(),
        session_maker=get_session_maker(),
        object_store=get_object_store(),
    )
    return build_query_agent(settings, toolbox)


@router.post("/{video_id}/ask", response_model=AskResponse)
async def ask_video(
    video_id: str,
    body: AskRequest,
    _settings: Annotated[object, Depends(get_settings)],
) -> AskResponse:
    """動画について自然言語で質問し、引用つき回答を得る."""
    try:
        agent = get_query_agent()
    except AgentUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail=f"query agent unavailable: {e}",
        ) from e

    try:
        answer = await ask(agent, body.question, video_id=video_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"agent failed: {e}") from e

    return AskResponse(video_id=video_id, question=body.question, answer=answer)
