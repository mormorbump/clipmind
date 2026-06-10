"""LLMProvider Protocol (ADR-0003).

「テキスト生成」と「画像つき生成 (vision)」の 2 メソッドだけの薄い抽象.
実装は anthropic / openai SDK を直接使う (LangChain Agent は Phase 5 で別途).

リトライ + フォールバックは `FallbackLLMProvider` が担う:
  1. primary を最大 max_retries 回 (指数バックオフ)
  2. だめなら secondary へ切替
  3. 両方失敗で LLMUnavailableError
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable


class LLMUnavailableError(RuntimeError):
    """全プロバイダが失敗した."""


@runtime_checkable
class LLMProvider(Protocol):
    """LLM 呼び出しの最小抽象."""

    @property
    def name(self) -> str:
        """プロバイダ識別子 (ログ・DB 記録用)."""
        ...

    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        """テキスト生成."""
        ...

    async def generate_with_image(
        self, prompt: str, image_jpeg: bytes, *, max_tokens: int = 1024
    ) -> str:
        """画像つき生成 (vision)."""
        ...


class AnthropicProvider:
    """Anthropic Claude (vision 対応)."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        self._api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return f"anthropic/{self.model}"

    def _client(self) -> object:
        import anthropic

        return anthropic.AsyncAnthropic(api_key=self._api_key)

    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        client = self._client()
        resp = await client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(resp.content[0].text)

    async def generate_with_image(
        self, prompt: str, image_jpeg: bytes, *, max_tokens: int = 1024
    ) -> str:
        import base64

        client = self._client()
        resp = await client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(image_jpeg).decode(),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return str(resp.content[0].text)


class OpenAIProvider:
    """OpenAI GPT (vision 対応)."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return f"openai/{self.model}"

    def _client(self) -> object:
        import openai

        return openai.AsyncOpenAI(api_key=self._api_key)

    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        client = self._client()
        resp = await client.chat.completions.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(resp.choices[0].message.content)

    async def generate_with_image(
        self, prompt: str, image_jpeg: bytes, *, max_tokens: int = 1024
    ) -> str:
        import base64

        client = self._client()
        b64 = base64.b64encode(image_jpeg).decode()
        resp = await client.chat.completions.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return str(resp.choices[0].message.content)


class FallbackLLMProvider:
    """リトライ + プロバイダ切替を担うラッパー (ADR-0003 §プロバイダ障害時).

    1. primary を max_retries 回 (指数バックオフ: base_delay * 2^attempt)
    2. 失敗したら secondary を同様に
    3. 全滅で LLMUnavailableError
    """

    def __init__(
        self,
        primary: LLMProvider,
        secondary: LLMProvider | None = None,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.max_retries = max_retries
        self.base_delay = base_delay

    @property
    def name(self) -> str:
        return f"fallback({self.primary.name})"

    async def _try_provider(
        self,
        provider: LLMProvider,
        prompt: str,
        image_jpeg: bytes | None,
        max_tokens: int,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                if image_jpeg is None:
                    return await provider.generate(prompt, max_tokens=max_tokens)
                return await provider.generate_with_image(prompt, image_jpeg, max_tokens=max_tokens)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay * (2**attempt))
        msg = f"{provider.name} failed after {self.max_retries} retries: {last_error}"
        raise LLMUnavailableError(msg)

    async def _generate(self, prompt: str, image_jpeg: bytes | None, max_tokens: int) -> str:
        try:
            return await self._try_provider(self.primary, prompt, image_jpeg, max_tokens)
        except LLMUnavailableError:
            if self.secondary is None:
                raise
            return await self._try_provider(self.secondary, prompt, image_jpeg, max_tokens)

    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        return await self._generate(prompt, None, max_tokens)

    async def generate_with_image(
        self, prompt: str, image_jpeg: bytes, *, max_tokens: int = 1024
    ) -> str:
        return await self._generate(prompt, image_jpeg, max_tokens)
