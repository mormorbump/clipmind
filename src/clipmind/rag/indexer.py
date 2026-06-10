"""Qdrant への segment インデックス + ハイブリッド検索 (Phase 3).

- dense: EmbeddingProvider (ADR-0010)
- sparse: Qdrant/bm25 (fastembed) を named sparse vector に格納
- ハイブリッド: Qdrant Query API の prefetch + RRF fusion (サーバー側)

コレクション名は `segments__{model_tag}` でモデルごとに分離し、
ベクトル空間の混在を構造的に防ぐ.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from clipmind.rag.embeddings import EmbeddingProvider, collection_tag

if TYPE_CHECKING:
    from clipmind.rag.fuse import TimelineSegment

DENSE_NAME = "dense"
SPARSE_NAME = "bm25"
_NAMESPACE = uuid.UUID("b7e23ec2-9277-4dd4-b3d4-31b03cee71cb")  # ClipMind 固有 namespace


@dataclass(frozen=True)
class SearchHit:
    """検索結果 1 件."""

    video_id: str
    start_ms: int
    end_ms: int
    text: str
    score: float


@lru_cache(maxsize=1)
def _bm25_model() -> Any:
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(model_name="Qdrant/bm25")


def _bm25_embed(texts: list[str]) -> list[models.SparseVector]:
    model = _bm25_model()
    return [
        models.SparseVector(indices=emb.indices.tolist(), values=emb.values.tolist())
        for emb in model.embed(texts)
    ]


def _point_id(video_id: UUID, start_ms: int) -> str:
    """再 Ingest 時に同じ窓を上書きできる決定的 ID."""
    return str(uuid.uuid5(_NAMESPACE, f"{video_id}:{start_ms}"))


class SegmentIndex:
    """segment 単位の Qdrant インデックス."""

    def __init__(self, qdrant_url: str, embedder: EmbeddingProvider) -> None:
        self.client = AsyncQdrantClient(url=qdrant_url)
        self.embedder = embedder
        self.collection = f"segments__{collection_tag(embedder)}"

    async def ensure_collection(self) -> None:
        """コレクションが無ければ作成 (dense + sparse named vectors)."""
        if await self.client.collection_exists(self.collection):
            return
        await self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                DENSE_NAME: models.VectorParams(
                    size=self.embedder.dimension, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                SPARSE_NAME: models.SparseVectorParams(
                    modifier=models.Modifier.IDF  # BM25 は IDF modifier 必須
                )
            },
        )

    async def index_segments(self, segments: list[TimelineSegment]) -> int:
        """segment 列を upsert する. 返り値は登録件数."""
        if not segments:
            return 0
        await self.ensure_collection()

        texts = [s.search_text for s in segments]
        dense = await asyncio.to_thread(self.embedder.embed_texts, texts)
        sparse = await asyncio.to_thread(_bm25_embed, texts)

        points = [
            models.PointStruct(
                id=_point_id(seg.video_id, seg.start_ms),
                vector={DENSE_NAME: dense[i], SPARSE_NAME: sparse[i]},
                payload={
                    "video_id": str(seg.video_id),
                    "start_ms": seg.start_ms,
                    "end_ms": seg.end_ms,
                    "text": seg.search_text,
                },
            )
            for i, seg in enumerate(segments)
        ]
        await self.client.upsert(collection_name=self.collection, points=points)
        return len(points)

    def _video_filter(self, video_id: str | None) -> models.Filter | None:
        if video_id is None:
            return None
        return models.Filter(
            must=[models.FieldCondition(key="video_id", match=models.MatchValue(value=video_id))]
        )

    @staticmethod
    def _to_hits(points: list[models.ScoredPoint]) -> list[SearchHit]:
        hits = []
        for p in points:
            payload = p.payload or {}
            hits.append(
                SearchHit(
                    video_id=str(payload.get("video_id", "")),
                    start_ms=int(payload.get("start_ms", 0)),
                    end_ms=int(payload.get("end_ms", 0)),
                    text=str(payload.get("text", "")),
                    score=float(p.score),
                )
            )
        return hits

    async def search_dense(
        self, query: str, *, top_k: int = 5, video_id: str | None = None
    ) -> list[SearchHit]:
        """dense のみの検索 (M3-2)."""
        vector = await asyncio.to_thread(self.embedder.embed_query, query)
        result = await self.client.query_points(
            collection_name=self.collection,
            query=vector,
            using=DENSE_NAME,
            limit=top_k,
            query_filter=self._video_filter(video_id),
            with_payload=True,
        )
        return self._to_hits(result.points)

    async def search_hybrid(
        self, query: str, *, top_k: int = 5, video_id: str | None = None, prefetch_k: int = 20
    ) -> list[SearchHit]:
        """dense + BM25 を RRF で融合するハイブリッド検索 (M3-3).

        Qdrant Query API の prefetch + FusionQuery(RRF) でサーバー側融合.
        """
        dense_vec = await asyncio.to_thread(self.embedder.embed_query, query)
        sparse_vec = (await asyncio.to_thread(_bm25_embed, [query]))[0]
        flt = self._video_filter(video_id)

        result = await self.client.query_points(
            collection_name=self.collection,
            prefetch=[
                models.Prefetch(query=dense_vec, using=DENSE_NAME, limit=prefetch_k, filter=flt),
                models.Prefetch(query=sparse_vec, using=SPARSE_NAME, limit=prefetch_k, filter=flt),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return self._to_hits(result.points)

    async def delete_video(self, video_id: str) -> None:
        """動画削除時に該当 segment を全削除."""
        if not await self.client.collection_exists(self.collection):
            return
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=self._video_filter(video_id) or models.Filter()
            ),
        )

    async def close(self) -> None:
        await self.client.close()
