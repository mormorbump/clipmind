# ClipMind — 評価戦略

> 「作っただけ」で終わらせないための、定量的・再現可能な評価設計。

面接で必ず聞かれる「精度はどう測った？」「何と比較した？」に明確に答えることを目的とする。

---

## 1. 評価の3レイヤー

```
┌──────────────────────────────────┐
│ L3: エンドツーエンド回答品質      │  ← LLM-as-judge / Ragas / 手動
├──────────────────────────────────┤
│ L2: Retrieval 精度                │  ← Recall@k, MRR, nDCG
├──────────────────────────────────┤
│ L1: 下流コンポーネント            │  ← Whisper WER, YOLO mAP, Caption BLEU
└──────────────────────────────────┘
```

---

## 2. L1: コンポーネント単体評価

### 2.1 Whisper 書き起こし
- **指標**: WER (Word Error Rate)
- **データ**: LibriSpeech test-clean（英語）+ 自作日本語セット（10分）
- **比較対象**: `base` vs `small` vs `medium` vs `large-v3`
- **目標**: 英語 WER < 8%, 日本語 WER < 15%

### 2.2 YOLO 物体検知
- **指標**: mAP@0.5, mAP@0.5:0.95
- **データ**: COCO val2017 のサブセット（100枚）
- **比較対象**: `yolov8n` vs `yolov8s` vs `yolov8m`
- **目標**: mAP@0.5 > 0.6（n）, > 0.7（s）

### 2.3 マルチモーダル キャプション
- **指標**: BLEU-4, ROUGE-L, CLIP-Score（画像とキャプションの整合性）
- **データ**: 自作 100 フレーム × 人手正解
- **比較対象**: Claude Sonnet 4.6 / Claude Haiku 4.5 / GPT-4o / GPT-4o-mini
- **目標**: CLIP-Score > 0.30

---

## 3. L2: Retrieval 精度

### 3.1 評価データセット

**作成方法**:
1. 自分で録画した動画 10 本（計 2 時間程度）を Ingest
2. 各動画について「特定タイムスタンプに関する質問」を人手で 5 個作成
   - 例: Q: 「プレゼンターがスライドを切り替えたのはいつ？」 → 正解: [120000ms, 185000ms]
3. 合計 **50 クエリ** × 動画メタデータの評価セット

ファイル形式:
```jsonl
{"query": "...", "video_id": "vid_001", "relevant_segments": [{"start_ms": 120000, "end_ms": 125000}], "tags": ["temporal"]}
```

### 3.2 指標
| 指標 | 計算 | 目標 |
|---|---|---|
| Recall@5 | 正解 segment が上位5件に入った割合 | > 0.7 |
| Recall@10 | 上位10件 | > 0.85 |
| MRR | 最初にヒットした順位の逆数平均 | > 0.6 |
| nDCG@5 | ランク考慮の指標 | > 0.65 |

### 3.3 比較実験
| バリエーション | 目的 |
|---|---|
| Dense のみ | ベースライン |
| Sparse (BM25) のみ | 表層一致の強さ |
| Dense + BM25（RRF）| ハイブリッド |
| Dense + BM25 + Rerank | 完全版 |

各バリエーションで上記指標を測り、表にまとめる（面接で即座に見せる）。

### 3.4 Chunk サイズ実験
- Window 幅: 5s / 15s / 30s / 60s
- 各幅で Recall@5 を比較し、最適値を特定

---

## 4. L3: エンドツーエンド回答品質

### 4.1 Ragas による自動評価
```python
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
from ragas import evaluate

result = evaluate(
    dataset,
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    llm=claude_sonnet,
    embeddings=openai_embed,
)
```

**指標**:
- `faithfulness`: 生成回答が検索コンテキストに忠実か（ハルシネーション検出）
- `answer_relevancy`: 質問に対する回答の関連性
- `context_precision`: 検索コンテキストの精度
- `context_recall`: 検索コンテキストの網羅性

**目標**: 各指標 > 0.75

### 4.2 LLM-as-judge
GPT-4o を judge として、以下 3 観点で 1〜5 のスコアリング:
1. **正確性**: 回答が動画内容と一致しているか
2. **引用妥当性**: 提示された timestamp が正しいか
3. **情報量**: 不要な冗長性がないか

評価セット: 上記 50 クエリを使用。

### 4.3 人手評価（最終チェック）
- 自分で 20 クエリを走らせ、5 段階評価
- Ragas / LLM-as-judge との相関を取ることで、自動評価の信頼性も検証

---

## 5. 継続的評価（CE）

### 5.1 評価バッチの自動実行
```bash
make eval              # ローカル
# CI上は PR マージ時に limited セット（10クエリ）で回帰検出
```

### 5.2 メトリクス可視化
- Prometheus + Grafana に `rag_recall_at_5{version="v1.2"}` を push
- リリース跨ぎで精度が下がっていないか監視

### 5.3 評価レポート
`docs/eval-reports/` 以下に日時別のレポート（Markdown）を git commit し、学びをログ化。

---

## 6. 評価で「学び」を記録する

各評価実行後に `docs/learning-log.md` に以下を残す:

```
## 2026-05-xx — Retrieval 実験 #3
- Chunk 5s: Recall@5 = 0.52
- Chunk 15s: Recall@5 = 0.74
- Chunk 30s: Recall@5 = 0.68

考察: 15s がスイートスポット。短すぎると文脈不足、長すぎるとノイズ増。
次アクション: 15s を固定して Rerank の効果を測る。
```

→ 面接で「どういう試行錯誤をしましたか？」に即答できる状態を作る。

---

## 7. 評価関連の ADR

詳細な意思決定は [adr/0006-evaluation-strategy.md](adr/0006-evaluation-strategy.md)。
