"""フレームキャプション生成の抽象 (M2-2).

ADR-0003 の使い分け: キャプションは大量呼び出しなので
主 = OpenAI gpt-4o-mini / フォールバック = Claude Haiku.

API キーが無い環境では `NullCaptioner` が使われ、キャプションなしで Ingest が継続する
(部分失敗時の Ingest 継続方針).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from clipmind.llm.provider import LLMProvider

CAPTION_PROMPT = (
    "Describe this video frame in one concise sentence. "
    "Focus on visible objects, people, actions, and any readable text. "
    "Reply with the sentence only."
)


@dataclass(frozen=True)
class CaptionResult:
    """キャプション 1 件."""

    text: str
    model: str


@runtime_checkable
class Captioner(Protocol):
    """フレーム画像 1 枚 → 説明文."""

    async def caption(self, image_jpeg: bytes) -> CaptionResult | None:
        """キャプションを返す. 生成不能 (キー無し等) なら None."""
        ...


class LLMCaptioner:
    """LLMProvider 経由のキャプション生成."""

    def __init__(self, provider: LLMProvider, *, max_tokens: int = 200) -> None:
        self.provider = provider
        self.max_tokens = max_tokens

    async def caption(self, image_jpeg: bytes) -> CaptionResult | None:
        text = await self.provider.generate_with_image(
            CAPTION_PROMPT, image_jpeg, max_tokens=self.max_tokens
        )
        return CaptionResult(text=text.strip(), model=self.provider.name)


class NullCaptioner:
    """API キーが無い環境用: 常に None (キャプションなしで Ingest 継続)."""

    async def caption(self, image_jpeg: bytes) -> CaptionResult | None:
        return None
