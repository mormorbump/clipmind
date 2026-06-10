"""Rerank 抽象 (M3-4).

上位 prefetch_k 件を意味的に再ランクして top_k に絞る.
- NullReranker: 何もしない (デフォルト)
- CrossEncoderReranker: fastembed の TextCrossEncoder (ローカル, キー不要)
- Cohere Rerank は API キー投入後の選択肢として将来追加
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Protocol, runtime_checkable

from clipmind.rag.indexer import SearchHit


@runtime_checkable
class Reranker(Protocol):
    """検索結果の再ランク抽象."""

    async def rerank(self, query: str, hits: list[SearchHit], *, top_k: int) -> list[SearchHit]:
        """hits を query との関連度で並べ替えて top_k 件返す."""
        ...


class NullReranker:
    """再ランクなし: スコア順のまま top_k に切るだけ."""

    async def rerank(self, query: str, hits: list[SearchHit], *, top_k: int) -> list[SearchHit]:
        return hits[:top_k]


@lru_cache(maxsize=1)
def _cross_encoder(model_name: str) -> Any:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=model_name)


class CrossEncoderReranker:
    """fastembed TextCrossEncoder によるローカル再ランク."""

    def __init__(self, model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name

    async def rerank(self, query: str, hits: list[SearchHit], *, top_k: int) -> list[SearchHit]:
        if not hits:
            return []
        model = _cross_encoder(self.model_name)
        scores = await asyncio.to_thread(lambda: list(model.rerank(query, [h.text for h in hits])))
        ranked = sorted(zip(scores, hits, strict=True), key=lambda t: t[0], reverse=True)
        return [
            SearchHit(
                video_id=h.video_id,
                start_ms=h.start_ms,
                end_ms=h.end_ms,
                text=h.text,
                score=float(s),
            )
            for s, h in ranked[:top_k]
        ]
