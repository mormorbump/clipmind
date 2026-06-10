"""Query Agent (M5-2).

LangChain 1.x の `create_agent` (LangGraph ベース) を使った tool-calling agent.
knowledge/langgraph/02 の整理どおり、「ユーザー対話 = 動的なツール選択」なので
StateGraph を自作せず Agent Loop に任せる.

実 LLM が必要. キーが無い環境では `AgentUnavailableError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clipmind.agents.tools import QueryToolbox, build_tools
from clipmind.config import Settings

if TYPE_CHECKING:
    pass

SYSTEM_PROMPT = """\
You are ClipMind, an assistant that answers questions about ingested videos.

Rules:
- Always ground answers in tool results. Use hybrid_search first for content questions.
- Include timestamps (mm:ss) in answers so the user can jump to the moment.
- When the user asks about a specific video, pass its video_id to every tool call.
- If search returns nothing relevant, say so honestly. Never invent video content.
- Answer in the same language as the user's question.
"""


class AgentUnavailableError(RuntimeError):
    """LLM API キーが無く Agent を構築できない."""


def _build_chat_model(settings: Settings) -> Any:
    """ADR-0003: 対話 Agent は Claude 優先、無ければ OpenAI."""
    if settings.anthropic_api_key:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            timeout=60,
        )
    if settings.openai_api_key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key)
    msg = "no LLM API key configured (ANTHROPIC_API_KEY / OPENAI_API_KEY)"
    raise AgentUnavailableError(msg)


def build_query_agent(settings: Settings, toolbox: QueryToolbox) -> Any:
    """tool-calling agent を構築して返す.

    Returns:
        LangGraph CompiledStateGraph. `ainvoke({"messages": [...]})` で実行する.
    """
    from langchain.agents import create_agent

    model = _build_chat_model(settings)
    return create_agent(
        model=model,
        tools=build_tools(toolbox),
        system_prompt=SYSTEM_PROMPT,
    )


async def ask(agent: Any, question: str, *, video_id: str | None = None) -> str:
    """1 問 1 答ヘルパ. video_id があれば質問に文脈として付与する."""
    content = question if video_id is None else f"[video_id: {video_id}]\n{question}"
    result = await agent.ainvoke({"messages": [{"role": "user", "content": content}]})
    last = result["messages"][-1]
    return str(last.content)
