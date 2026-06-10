"""Settings から EmbeddingProvider / SegmentIndex / Reranker を組み立てる.

ADR-0010: OpenAI キーがあれば text-embedding-3-small、無ければ fastembed (ローカル).
"""

from __future__ import annotations

from clipmind.config import Settings
from clipmind.rag.embeddings import (
    EmbeddingProvider,
    FastEmbedProvider,
    OpenAIEmbeddingProvider,
)
from clipmind.rag.indexer import SegmentIndex
from clipmind.rag.reranker import CrossEncoderReranker, NullReranker, Reranker


def build_embedder(settings: Settings) -> EmbeddingProvider:
    """キー有無で embedding プロバイダを切替."""
    if settings.openai_api_key:
        return OpenAIEmbeddingProvider(settings.openai_api_key)
    return FastEmbedProvider()


def build_segment_index(settings: Settings) -> SegmentIndex:
    """Qdrant インデックスを構築."""
    return SegmentIndex(settings.qdrant_url, build_embedder(settings))


def build_reranker(settings: Settings) -> Reranker:
    """Reranker を構築 (デフォルト off)."""
    if settings.enable_rerank:
        return CrossEncoderReranker()
    return NullReranker()
