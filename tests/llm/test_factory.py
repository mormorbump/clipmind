"""factory のキー有無による分岐検証."""

from __future__ import annotations

from clipmind.config import Settings
from clipmind.llm.captioner import LLMCaptioner, NullCaptioner
from clipmind.llm.factory import build_caption_provider, build_captioner


def _settings(**kw: str) -> Settings:
    base = {"anthropic_api_key": "", "openai_api_key": ""}
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


def test_no_keys_returns_null_captioner() -> None:
    settings = _settings()
    assert build_caption_provider(settings) is None
    assert isinstance(build_captioner(settings), NullCaptioner)


def test_openai_only() -> None:
    settings = _settings(openai_api_key="sk-test")  # pragma: allowlist secret
    provider = build_caption_provider(settings)
    assert provider is not None
    assert "openai" in provider.primary.name
    assert provider.secondary is None
    assert isinstance(build_captioner(settings), LLMCaptioner)


def test_both_keys_openai_primary_anthropic_secondary() -> None:
    settings = _settings(
        openai_api_key="sk-test",  # pragma: allowlist secret
        anthropic_api_key="sk-ant-test",  # pragma: allowlist secret
    )
    provider = build_caption_provider(settings)
    assert provider is not None
    assert "openai" in provider.primary.name
    assert provider.secondary is not None
    assert "anthropic" in provider.secondary.name
