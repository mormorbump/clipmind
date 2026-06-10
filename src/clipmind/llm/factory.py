"""Settings から Captioner / LLMProvider を組み立てる factory.

ADR-0003 の使い分け:
  - キャプション (大量呼び出し): 主 OpenAI gpt-4o-mini / 副 Claude Haiku
  - API キーが両方無ければ NullCaptioner (キャプションなしで Ingest 継続)
"""

from __future__ import annotations

from clipmind.config import Settings
from clipmind.llm.captioner import Captioner, LLMCaptioner, NullCaptioner
from clipmind.llm.provider import (
    AnthropicProvider,
    FallbackLLMProvider,
    LLMProvider,
    OpenAIProvider,
)


def build_caption_provider(settings: Settings) -> LLMProvider | None:
    """キャプション用 LLMProvider (主 OpenAI / 副 Anthropic). キー無しなら None."""
    openai_provider = (
        OpenAIProvider(settings.openai_api_key, model=settings.caption_model_openai)
        if settings.openai_api_key
        else None
    )
    anthropic_provider = (
        AnthropicProvider(settings.anthropic_api_key, model=settings.caption_model_anthropic)
        if settings.anthropic_api_key
        else None
    )

    if openai_provider and anthropic_provider:
        return FallbackLLMProvider(openai_provider, anthropic_provider)
    if openai_provider:
        return FallbackLLMProvider(openai_provider)
    if anthropic_provider:
        return FallbackLLMProvider(anthropic_provider)
    return None


def build_captioner(settings: Settings) -> Captioner:
    """Settings から Captioner を構築. キー無しなら NullCaptioner."""
    provider = build_caption_provider(settings)
    if provider is None:
        return NullCaptioner()
    return LLMCaptioner(provider)
