# ADR 0002: Vector DB は Qdrant に単一化する

## ステータス
Accepted — 2026-04-25

## コンテキスト

ベクトル検索用 DB の選択肢は多数ある:
- Pinecone（SaaS）
- Milvus（OSS）
- Chroma（OSS、軽量）
- Qdrant（OSS、Rust製）
- Weaviate（OSS）
- pgvector（Postgres拡張）

設計ドラフトでは「Chroma（開発）+ Qdrant（本番）」という二段構えを想定したが、
レビューで「個人プロジェクトで抽象化層を書くのは工数浪費。Qdrant 単体で両方カバー可能」と指摘された。

## 検討した選択肢

### A. Pinecone
- Pros: セットアップ不要、ドキュメント充実
- Cons: SaaS 依存、無料枠制限、ローカル開発できない

### B. Chroma
- Pros: pip install だけで動く、ローカル開発最速
- Cons: 本番運用では機能不足、sparse vector 非対応

### C. Qdrant
- Pros: ローカル（Docker）でも本番でも同じ、sparse vector + dense の両対応、Rust で高速
- Cons: Chroma より起動コスト高い（Docker 必須）

### D. pgvector
- Pros: Postgres 一つで済む
- Cons: sparse vector 未対応、SPARK + dense のハイブリッド実装が煩雑

## 決定

**C. Qdrant に一本化**。開発も本番も同じ Docker イメージで動かす。

理由:
1. sparse vector（BM25）+ dense のハイブリッドを同一 DB で完結できる
2. docker-compose で 10 秒で起動する
3. 個人学習プロジェクトで複数 DB の抽象化層を書く価値はない（YAGNI）
4. 面接で「なぜ Qdrant？」と聞かれたときの説明が明確

## 影響・トレードオフ

- 開発環境でも Docker 前提になるため、macOS の初心者には敷居が上がる（このプロジェクトの想定ユーザーではないので許容）
- Pinecone / Milvus との比較経験は得られないが、ADR で「検討したが不採用」を明記することで経験不足を補う
- コレクション設計は要検討: `clipmind_segments`（1 collection × すべての動画）で payload filter により video_id で絞る方式

## 参考実装方針

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, SparseVectorParams

client = QdrantClient(url="http://localhost:6333")
client.create_collection(
    collection_name="clipmind_segments",
    vectors_config={
        "dense": VectorParams(size=1536, distance=Distance.COSINE),
    },
    sparse_vectors_config={
        "bm25": SparseVectorParams(),
    },
)
```
