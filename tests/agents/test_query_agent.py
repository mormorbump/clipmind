"""Query Agent 構築のテスト.

実 LLM 呼び出しはキー必須なので e2e マーカー. unit はキー無しエラーのみ.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clipmind.agents.query_agent import AgentUnavailableError, build_query_agent
from clipmind.agents.tools import QueryToolbox
from clipmind.config import Settings
from clipmind.storage.object_store import LocalFSObjectStore


def _toolbox(tmp_path: Path) -> QueryToolbox:
    from tests.agents.test_tools import FakeSegmentIndex

    return QueryToolbox(
        segment_index=FakeSegmentIndex(),  # type: ignore[arg-type]
        session_maker=None,  # type: ignore[arg-type]
        object_store=LocalFSObjectStore(base_dir=tmp_path / "objects"),
    )


def test_build_query_agent_without_keys_raises(tmp_path: Path) -> None:
    settings = Settings(anthropic_api_key="", openai_api_key="")
    with pytest.raises(AgentUnavailableError):
        build_query_agent(settings, _toolbox(tmp_path))


@pytest.mark.e2e
async def test_agent_answers_with_real_llm(tmp_path: Path) -> None:
    """実 LLM で 1 問 1 答 (要 ANTHROPIC_API_KEY / OPENAI_API_KEY)."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        pytest.skip("no LLM API key")

    from clipmind.agents.query_agent import ask

    settings = Settings()
    agent = build_query_agent(settings, _toolbox(tmp_path))
    answer = await ask(agent, "What does the video say about q3 results?", video_id="vid-1")
    assert isinstance(answer, str)
    assert len(answer) > 0
