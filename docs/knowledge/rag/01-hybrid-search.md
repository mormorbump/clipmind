# RAG: Chunking・Hybrid Search・Rerank

> 関連: ADR-0006, `docs/architecture.md` §5, `docs/evaluation.md`, Phase 3 / 4

## RAG = Retrieval Augmented Generation

LLM の知識は「学習時点」で凍結されている。動画コンテンツのような **「動的・閉じたデータ」**
について答えさせるには、外部から関連情報を引いてプロンプトに注入する必要がある。
これが RAG。

```
[query] ──► [Retriever] ──► relevant chunks ──┐
                                              ├─► [LLM] ──► answer
                       [System Prompt] ───────┘
```

精度を決めるのは **「LLM 部分」よりも「Retriever 部分」**。
ClipMind でも、回答品質の差はほぼ Retrieval の差に由来する。

---

## 1. Chunking — RAG の最重要設計

「動画 1 本」をそのままベクトル化しても役に立たない。
**意味のある単位（chunk / segment）に分割** してから embedding する。

### 1.1 ClipMind の chunk 単位

`fuse_node` が 5 秒（可変）の時間窓で fuse した segment が chunk になる:

```python
{
  "start_ms": 120000,
  "end_ms": 125000,
  "transcript": "let me show you the Q3 results",
  "objects": ["person", "laptop"],
  "captions": ["A presenter stands in front of slide..."],
  "key_frame_index": 642,
}
```

複数モダリティ（音声・物体・キャプション）を **1 つのテキストに連結** して embedding する。

### 1.2 Chunk サイズのトレードオフ

| 短すぎ（5s） | 長すぎ（60s） |
|---|---|
| 文脈不足 | ノイズ過多 |
| Recall は上がるが回答精度が落ちる | 引用 timestamp が粗くなる |

**実験ありき**。ClipMind では 5s / 15s / 30s / 60s で Recall@5 を比較し、最適値を選ぶ（`docs/evaluation.md` §3.4）。

---

## 2. 検索の 3 系統

### 2.1 Dense（意味検索）

- テキストを embedding（ベクトル）に変換し、コサイン類似度で検索
- ClipMind: `text-embedding-3-small`（1536 次元）
- 強み: **言い換え・概念マッチに強い**（「動画」≒「映像」）
- 弱み: **固有名詞・数字・時刻表現に弱い**（「Q3」と「third quarter」が必ずしも近くない）

### 2.2 Sparse / BM25（語彙検索）

- 単語の出現頻度ベースのランキング（TF-IDF の親戚）
- 強み: **完全一致・固有名詞に強い**
- 弱み: **同義語・言い換えに弱い**

### 2.3 ハイブリッド（Dense + Sparse）

両方の弱みを補い合う。**ClipMind の主役構成**。

```
[query]
   ├──► Dense  top_20 ──┐
   │                    ├─► RRF でマージ ──► top_20
   └──► BM25   top_20 ──┘
```

実装は ADR-0002 の Qdrant の sparse vector 機能で **同一 DB / 同一クエリ** で完結できる。
BM25 を別 DB（Elasticsearch 等）に持つと運用負荷が高い。

---

## 3. RRF（Reciprocal Rank Fusion）

複数の検索結果を「**ランクの逆数**」で統合する古典的手法。

```
score(doc) = Σ_i 1 / (k + rank_i(doc))    # k は通常 60
```

- スコアの絶対値ではなく **ランキング順位** を使うので、Dense と BM25 のスコア尺度の違いを吸収できる
- ハイパラは `k` だけ。チューニング不要に近い

```python
def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)
```

---

## 4. Rerank — 上位の精度を底上げ

Retriever は recall（漏れの少なさ）を稼ぎ、Reranker は precision（上位の正しさ）を稼ぐ。

```
top_20 (Retriever)
   │
   ▼
Reranker（クロスエンコーダ）── 各 (query, doc) ペアを精密にスコアリング
   │
   ▼
top_5 を LLM へ
```

選択肢:

| 方式 | 例 | コスト |
|---|---|---|
| API | Cohere Rerank `rerank-english-v3.0` | $0.001/クエリ |
| ローカル | `bge-reranker-v2-m3` | GPU 推奨 |

Reranker の効果は劇的に出ることが多い（Recall@5 が +0.1〜0.2）。
ClipMind では両方を実装して評価で比較する（Phase 3 M3-4）。

---

## 5. クエリの前処理

### 5.1 HyDE（Hypothetical Document Embedding）

「クエリの embedding」より **「クエリへの仮想回答の embedding」** の方が doc に近い、というアイデア。

```
query: "Q3 の結論は？"
   │
   ▼ LLM で仮想回答を生成
"Q3 の結論は売上が前年比 12% 増加したこと"
   │
   ▼ この文章で embedding
```

精度向上の余地はあるが、LLM 呼び出しが 1 回増える。**重要度: 中**。

### 5.2 Multi-query / Query expansion

クエリを LLM で 3〜5 通りに言い換え、それぞれで検索 → 統合。
コストとレイテンシが上がるので、ClipMind では当初は採用しない。

---

## 6. ハマりどころ

### 6.1 Embedding モデルを途中で変えると全 reindex が必要
- ベクトル空間が違うので、過去の embedding は使い物にならない
- ADR-0003 で `text-embedding-3-small` に固定している

### 6.2 chunk が小さすぎて文脈消失
- 評価で初めて気づく罠
- 「前後 2 chunk を加える `extended_context`」のような救済策あり

### 6.3 BM25 だけだと固有名詞ヒット率は高いが「意味」がズレる
- 「結論」と書かれていない部分は引けない
- Dense とのハイブリッド前提

### 6.4 Rerank は遅い
- ローカル `bge-reranker` は CPU だと数秒かかる
- 上位 20 件まで絞ってから rerank する

---

## 7. 実装で確認したいこと

- [ ] Dense のみ / BM25 のみ / Hybrid / Hybrid+Rerank の 4 構成で Recall@5 比較
- [ ] chunk サイズ 5s / 15s / 30s / 60s で Recall@5 比較
- [ ] Rerank の有無でレイテンシがどれだけ増えるか（p95）
- [ ] 失敗クエリのパターン分析（時刻表現が弱い、等）

数値は `docs/eval-reports/` に蓄積。

---

## 8. 参考リンク

- BM25 解説: https://en.wikipedia.org/wiki/Okapi_BM25
- RRF 元論文: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- Cohere Rerank: https://cohere.com/rerank
- BGE Reranker: https://huggingface.co/BAAI/bge-reranker-v2-m3
- HyDE: https://arxiv.org/abs/2212.10496

---

## 実践マーカー

- ✅ Phase 3 で実践
  - **fuse**: `src/clipmind/rag/fuse.py` — 5 秒窓で transcript / detection / caption を束ねて検索単位 (TimelineSegment) を生成。窓境界をまたぐ transcript は両方の窓に入れる
  - **dense**: `EmbeddingProvider` 抽象 (ADR-0010)。開発デフォルトは fastembed (bge-small-en-v1.5, 384 次元, ONNX, キー不要)、OpenAI キー投入で text-embedding-3-small に切替
  - **sparse (BM25)**: fastembed の `Qdrant/bm25` で sparse vector を生成し、Qdrant の named sparse vector (IDF modifier) に格納
  - **RRF 融合**: Qdrant Query API の `prefetch` + `FusionQuery(fusion=RRF)` で**サーバー側融合**。クライアントで RRF を自作する必要なし
  - **rerank**: `Reranker` Protocol + `CrossEncoderReranker` (fastembed TextCrossEncoder, ローカル)。デフォルト off (設定 `enable_rerank`)。Cohere はキー投入後の選択肢
- 検証済み (integration test): 意味検索 ("financial results presentation" → revenue セグメント)、キーワード混合 ("cat playing")、video_id フィルタ、決定的 point id (uuid5) による再 index 上書き
