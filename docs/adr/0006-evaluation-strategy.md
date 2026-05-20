# ADR 0006: 評価戦略 — Ragas + 自作データセット

## ステータス
Accepted — 2026-04-25

## コンテキスト

RAG / Agent 系プロジェクトで最も多い失敗は「評価が無い」こと。
「動いた」だけで終わると、採用面接で「精度はどう測った？」「何と比較した？」という質問に
答えられず、ポートフォリオ価値が半減する。

プロジェクト開始時から評価基盤を設計し、継続的評価（CE）を回す。

## 検討した選択肢

### 評価データセット

#### A. 既存ベンチマークを使う（MS MARCO, BEIR等）
- Pros: 定評ある、再現性
- Cons: 動画RAG に合うベンチマークが存在しない

#### B. 自作データセット
- Pros: プロジェクト要件に合う
- Cons: 作成コストがかかる（50 クエリ × 正解ラベル）

#### 決定: B. 自作 50 クエリ（`docs/evaluation.md` 参照）

### 評価フレームワーク

#### A. Ragas
- Pros: faithfulness, answer_relevancy, context_precision/recall 等、標準指標セットが揃う
- Cons: LLM を judge に使うためコストがかかる

#### B. DeepEval
- Pros: 単体テスト風に書ける、pytest 統合
- Cons: Ragas より機能は少ない

#### C. LangSmith の Evaluation
- Pros: LangChain エコシステムと統合
- Cons: SaaS 依存、有料

#### D. 完全自作（Recall@k, MRR のみ）
- Pros: 依存ゼロ
- Cons: 生成品質の評価が弱くなる

#### 決定: **A（Ragas）+ D（Retrieval 指標は自作）+ LLM-as-judge（独自）**

### LLM-as-judge のモデル

- judge には評価対象と**異なる**プロバイダのモデルを使う（バイアス回避）
- 評価対象: Claude Sonnet 4.6 で生成 → judge: GPT-4o
- 逆の構成でも一度回して、judge 間の一致率も測る

## 決定

### レイヤー

| レイヤー | 手法 | 頻度 |
|---|---|---|
| L1 コンポーネント | Whisper WER, YOLO mAP, Caption CLIP-Score | 初回のみ、主要変更時 |
| L2 Retrieval | Recall@k, MRR, nDCG（自作計算） | PR ごと（10クエリ小版）+ リリース前（50クエリ完全版）|
| L3 E2E | Ragas 4 指標 + LLM-as-judge + 人手 20件 | リリース前 |

### CI 統合

- PR 時: Retrieval 小版（10 クエリ）を自動実行。Recall@5 基準値を割ったら fail
- 夜間バッチ: 完全版（50 クエリ）+ Ragas を実行、レポートを git にコミット

### レポート

`docs/eval-reports/YYYY-MM-DD.md` に自動生成。
各レポートには以下を必ず含める:
- 評価実行日時
- 評価したバージョン（git SHA）
- 各指標の値
- 前回からの差分
- 失敗クエリのサンプル（学びに直結）

## 影響・トレードオフ

- 評価コストが月あたり $5〜10 発生する（Ragas の LLM 呼び出し）
  - `docs/cost-estimation.md` の予算内
- CI 実行時間が +2〜3 分増える
- 50 クエリを人手で作るのに 0.5〜1 日かかる（Phase 4 の工数に計上済み）

## 再検討トリガー

- プロジェクトが大規模化し、50 クエリでは網羅性不足になった場合
- Ragas のメジャーバージョンアップで指標が変わった場合
