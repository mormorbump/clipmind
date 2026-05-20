# RAG 評価: 3 レイヤーモデル

> 関連: ADR-0006, `docs/evaluation.md`, Phase 4

## なぜ評価が最重要なのか

「動いた」と「**役に立つ**」の間には深い溝がある。
RAG は LLM が文章を生成するため、**「もっともらしい嘘」が混入しやすい**。
評価がないプロジェクトは、

- 改善が「気のせい」になる（A/B 比較ができない）
- 面接で「精度は？」「何と比較した？」に答えられず瞬殺
- リリース後に劣化しても気付けない

→ プロジェクト開始時から評価設計を組み込む（ADR-0006）。

---

## 1. 3 レイヤー構造

```
┌──────────────────────────────────┐
│ L3: エンドツーエンド回答品質      │ Ragas / LLM-as-judge / 人手
├──────────────────────────────────┤
│ L2: Retrieval 精度                │ Recall@k / MRR / nDCG
├──────────────────────────────────┤
│ L1: コンポーネント単体            │ WER / mAP / CLIP-Score
└──────────────────────────────────┘
```

**下から上に積み上げる**。L1 が崩れていれば L2 も L3 も無意味。

---

## 2. L1: コンポーネント単体

| コンポーネント | 指標 | 目標 |
|---|---|---|
| Whisper | WER | 英 <8%, 日 <15% |
| YOLO | mAP@0.5 | >0.6 (n), >0.7 (s) |
| Caption (Vision LLM) | CLIP-Score, BLEU | CLIP > 0.30 |

評価頻度: 初回 + 主要モデル変更時のみ。CI には載せない（重い）。

---

## 3. L2: Retrieval 精度

### 3.1 評価データセット

「クエリ × 正解 segment」のペアが必要。
ClipMind では **自作 50 クエリ**（自分の動画 10 本 × 各 5 クエリ）。

```jsonl
{
  "query": "プレゼンターがスライドを切り替えたのはいつ？",
  "video_id": "vid_001",
  "relevant_segments": [{"start_ms": 120000, "end_ms": 125000}],
  "tags": ["temporal"]
}
```

### 3.2 主要指標

#### Recall@k
```
正解 segment が上位 k 件に入った割合
```
**最重要指標**。ClipMind 目標: Recall@5 > 0.7。

#### MRR（Mean Reciprocal Rank）
```
MRR = mean(1 / rank_of_first_correct)
```
「最初の正解が何位か」を平均。1 位なら 1.0、2 位なら 0.5。

#### nDCG@k（Normalized Discounted Cumulative Gain）
- ランクと relevance score（0/1 だけでなく 1〜3 段階）を考慮
- 複数の正解がある場合に MRR より精緻

### 3.3 比較実験のテンプレ

| 構成 | Recall@5 | MRR | レイテンシ p95 |
|---|---|---|---|
| Dense のみ | ? | ? | ? |
| BM25 のみ | ? | ? | ? |
| Hybrid (RRF) | ? | ? | ? |
| Hybrid + Rerank | ? | ? | ? |

**4 構成を全部測る** のが面接で語れる差別化ポイント。

---

## 4. L3: エンドツーエンド回答品質

### 4.1 Ragas（自動評価）

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

result = evaluate(
    dataset,
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    llm=claude_sonnet,
    embeddings=openai_embed,
)
```

| 指標 | 意味 |
|---|---|
| **faithfulness** | 回答が検索コンテキストに忠実か（**ハルシネーション検出**）|
| **answer_relevancy** | 質問への関連性 |
| **context_precision** | 検索結果の precision |
| **context_recall** | 検索結果の recall |

目標: 全指標 > 0.75。

### 4.2 LLM-as-judge

別モデル（GPT-4o）に「正確性 / 引用妥当性 / 情報量」を 1〜5 で採点させる。

**バイアス回避**: judge には **生成側と異なるプロバイダ**のモデルを使う（Claude で生成 → GPT で採点、逆も）。

### 4.3 人手評価

- 自動評価は LLM の癖に引きずられる
- 20 件だけ人手で採点し、自動評価との **相関係数** を取る
- 相関が低ければ自動評価の指標を見直す

---

## 5. CI 統合

```
PR 時:
  - 10 クエリ小版で Recall@5 を計算
  - 基準値（例: 0.65）を割ったら CI fail（リグレッション防止）
  - 実行時間 < 3 分

夜間バッチ:
  - 50 クエリ完全版 + Ragas
  - レポートを docs/eval-reports/YYYY-MM-DD.md に commit
```

---

## 6. レポートのフォーマット

毎回同じフォーマットで残すと比較が容易:

```markdown
# Eval Report 2026-05-01

- git SHA: abc1234
- 構成: hybrid + rerank-cohere
- chunk: 15s

| 指標 | 値 | 前回比 |
|---|---|---|
| Recall@5 | 0.78 | +0.04 |
| MRR | 0.62 | +0.02 |
| Ragas faithfulness | 0.82 | -0.01 |

## 失敗クエリ（学びの種）
1. "この動画の結論は？" → 動画末尾を引けず失敗。chunk 末尾優先のフラグ実装で改善見込み
```

→ 面接で「**どういう試行錯誤をしましたか**」に即答できる素材になる。

---

## 7. ハマりどころ

### 7.1 評価データセットの偏り
- 全クエリが「**時刻**」を尋ねるパターンだと、検索が時刻表現に過適応する
- `tags: ["temporal", "object", "topic", "summary"]` 等で **クエリ種別を分散** させる

### 7.2 LLM judge の自家中毒
- Claude が生成した回答を Claude で採点すると、**自分の文体に高得点を付ける**
- 必ず別プロバイダで採点

### 7.3 評価コストの暴走
- Ragas は内部で LLM を多数呼ぶ。50 クエリで $5〜10 飛ぶことも
- CI では 10 クエリ版に絞る（夜間バッチが完全版）

### 7.4 「平均値」だけ見て満足する
- 平均が良くても **特定カテゴリで壊滅的** ということがよくある
- tag 別に集計してヒートマップを出す

---

## 8. 実装で確認したいこと

- [ ] 50 クエリの評価セットを 1 日で作り切る
- [ ] Recall@k / MRR / nDCG の自作実装が公開実装と一致
- [ ] Ragas を 10 クエリで 3 分以内に回せる
- [ ] LLM-as-judge と人手評価の相関係数を取る

---

## 9. 参考リンク

- Ragas: https://docs.ragas.io/
- TREC 評価指標: https://trec.nist.gov/pubs/trec16/appendices/measures.pdf
- nDCG 解説: https://en.wikipedia.org/wiki/Discounted_cumulative_gain
- ADR-0006: `../adr/0006-evaluation-strategy.md`

---

## 実践マーカー

- 未実装（Phase 4 で着手予定）
