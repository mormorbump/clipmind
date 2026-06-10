"""FallbackLLMProvider のリトライ / フォールバック検証 (mock、API キー不要)."""

from __future__ import annotations

import pytest

from clipmind.llm.captioner import LLMCaptioner, NullCaptioner
from clipmind.llm.provider import FallbackLLMProvider, LLMUnavailableError


class FakeProvider:
    """呼び出し履歴を記録し、指定回数失敗してから成功する LLMProvider."""

    def __init__(self, name: str, *, fail_times: int = 0, reply: str = "ok") -> None:
        self._name = name
        self.fail_times = fail_times
        self.reply = reply
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            msg = f"{self._name} transient error"
            raise RuntimeError(msg)
        return self.reply

    async def generate_with_image(
        self,
        prompt: str,
        image_jpeg: bytes,
        *,
        max_tokens: int = 1024,
    ) -> str:
        return await self.generate("")


async def test_primary_success_no_fallback() -> None:
    """primary が 1 発成功なら secondary は呼ばれない."""
    primary = FakeProvider("p")
    secondary = FakeProvider("s")
    provider = FallbackLLMProvider(primary, secondary, base_delay=0.001)

    assert await provider.generate("hi") == "ok"
    assert primary.calls == 1
    assert secondary.calls == 0


async def test_primary_retries_then_succeeds() -> None:
    """primary が 2 回失敗 → 3 回目で成功 (リトライが効く)."""
    primary = FakeProvider("p", fail_times=2)
    provider = FallbackLLMProvider(primary, max_retries=3, base_delay=0.001)

    assert await provider.generate("hi") == "ok"
    assert primary.calls == 3


async def test_fallback_to_secondary() -> None:
    """primary 全滅 → secondary に切替."""
    primary = FakeProvider("p", fail_times=99)
    secondary = FakeProvider("s", reply="from-secondary")
    provider = FallbackLLMProvider(primary, secondary, max_retries=2, base_delay=0.001)

    assert await provider.generate("hi") == "from-secondary"
    assert primary.calls == 2
    assert secondary.calls == 1


async def test_all_fail_raises() -> None:
    """両方全滅で LLMUnavailableError."""
    primary = FakeProvider("p", fail_times=99)
    secondary = FakeProvider("s", fail_times=99)
    provider = FallbackLLMProvider(primary, secondary, max_retries=2, base_delay=0.001)

    with pytest.raises(LLMUnavailableError):
        await provider.generate("hi")


async def test_llm_captioner_strips_text() -> None:
    """LLMCaptioner が provider の出力を CaptionResult に包む."""
    provider = FakeProvider("p", reply="  A cat on a desk.  ")
    captioner = LLMCaptioner(FallbackLLMProvider(provider, base_delay=0.001))

    result = await captioner.caption(b"\xff\xd8fakejpeg")
    assert result is not None
    assert result.text == "A cat on a desk."
    assert "fallback" in result.model


async def test_null_captioner_returns_none() -> None:
    """NullCaptioner は常に None (キー無し環境)."""
    assert await NullCaptioner().caption(b"\xff\xd8fakejpeg") is None
