# ADR 0010: Embedding は Provider 抽象 + ローカル fastembed を開発デフォルトにする

## ステータス
Accepted — 2026-06-10

## コンテキスト

ADR-0003 では Embedding を「OpenAI text-embedding-3-small に固定」とした。
しかし Phase 3 実装時点で OpenAI API キーが未投入であり、
**キーなしでも RAG パイプライン全体（embedding → Qdrant → ハイブリッド検索 → 評価）を
動かして学習・テストできる**状態が必要になった。

Embedding はモデルを切り替えるとベクトル空間の互換性が無くなるため、
「どのモデルで埋め込んだか」を Qdrant コレクション名に刻む必要がある。

## 検討した選択肢

### A. OpenAI 固定のまま、キー投入まで Phase 3 を保留
- Pros: ADR-0003 と完全整合、コレクションが 1 つで済む
- Cons: キーが無いと Phase 3〜5 が全部止まる。CI で実 API を叩くことになる

### B. EmbeddingProvider 抽象 + fastembed (ローカル ONNX) を開発デフォルト
- Pros: キーなしで全パイプラインが動く。CI も外部 API 不要。
  fastembed は Qdrant 公式のローカル embedding ライブラリで親和性が高い
- Cons: 本番切替時に全 embedding の再計算が必要（ただしこれは ADR-0003 でも明記済みのリスク）

### C. sentence-transformers
- Pros: モデル選択肢が広い
- Cons: torch 依存が重い（ultralytics で既に入っているが、fastembed は ONNX で軽量・高速）

## 決定

**B. EmbeddingProvider Protocol を切り、開発デフォルトは fastembed**

```python
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...        # 例: "fastembed/bge-small-en-v1.5"
    @property
    def dimension(self) -> int: ...   # 例: 384
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
```

- デフォルト実装: `FastEmbedProvider` (BAAI/bge-small-en-v1.5, 384 次元, ONNX)
- OpenAI キーがあれば `OpenAIEmbeddingProvider` (text-embedding-3-small, 1536 次元)
- **Qdrant コレクション名にモデルタグを含める** (`segments__bge_small_en_v1_5` 等) ことで、
  モデル切替時の空間非互換を構造的に防ぐ
- Sparse (BM25) は Qdrant 公式の `Qdrant/bm25` (fastembed) で生成し、
  Qdrant の named sparse vector に格納。ハイブリッドは Query API の RRF fusion をサーバー側で実行

## 影響・トレードオフ

- ADR-0003 の「text-embedding-3-small 固定」を **「本番デフォルト」に格下げ**し、
  開発・CI はローカル embedding で回す二段構えに変更
- モデルごとにコレクションが分かれるため、切替時は再 Ingest（再 embedding）が必要 — 許容
- bge-small は英語寄り。日本語動画が主になったら `bge-m3` / `multilingual-e5` 系に切替を検討

## 将来の再検討トリガー

- 日本語クエリの Recall@5 が目標 (0.7) を下回った場合 → 多言語モデルへ
- OpenAI キー投入後の品質比較で text-embedding-3-small が大差で勝った場合 → 本番は OpenAI 固定
