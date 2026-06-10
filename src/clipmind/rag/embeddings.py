"""EmbeddingProvider 抽象 (ADR-0010).

開発デフォルト: fastembed (ローカル ONNX, BAAI/bge-small-en-v1.5, 384 次元).
OpenAI キーがあれば text-embedding-3-small (1536 次元) に切替可能.

モデルを切り替えるとベクトル空間の互換性が無いため、
`collection_tag` をコレクション名に刻んで構造的に混在を防ぐ.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """テキスト埋め込みの最小抽象."""

    @property
    def name(self) -> str:
        """モデル識別子."""
        ...

    @property
    def dimension(self) -> int:
        """ベクトル次元数."""
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """ドキュメント側の埋め込み."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """クエリ側の埋め込み (モデルによっては doc と異なる前処理)."""
        ...


def collection_tag(provider: EmbeddingProvider) -> str:
    """コレクション名に使える安全なモデルタグを返す."""
    return re.sub(r"[^a-z0-9]+", "_", provider.name.lower()).strip("_")


class FastEmbedProvider:
    """fastembed (ONNX) によるローカル埋め込み. API キー不要."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", dimension: int = 384) -> None:
        self.model_name = model_name
        self._dimension = dimension

    @property
    def name(self) -> str:
        return f"fastembed/{self.model_name.split('/')[-1]}"

    @property
    def dimension(self) -> int:
        return self._dimension

    @lru_cache(maxsize=1)  # noqa: B019  プロセス内モデルキャッシュが目的
    def _model(self) -> object:
        from fastembed import TextEmbedding

        return TextEmbedding(model_name=self.model_name)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._model()
        return [vec.tolist() for vec in model.embed(texts)]  # type: ignore[attr-defined]

    def embed_query(self, text: str) -> list[float]:
        model = self._model()
        return list(next(iter(model.query_embed(text))).tolist())  # type: ignore[attr-defined]


class OpenAIEmbeddingProvider:
    """OpenAI text-embedding-3-small (本番デフォルト, ADR-0003)."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._dimension = dimension

    @property
    def name(self) -> str:
        return f"openai/{self.model}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed(self, texts: list[str]) -> list[list[float]]:
        import openai

        client = openai.OpenAI(api_key=self._api_key)
        resp = client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]
