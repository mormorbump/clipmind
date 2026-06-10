"""LLM プロバイダ抽象 (ADR-0003)."""

from clipmind.llm.captioner import Captioner, CaptionResult
from clipmind.llm.provider import LLMProvider, LLMUnavailableError

__all__ = ["CaptionResult", "Captioner", "LLMProvider", "LLMUnavailableError"]
