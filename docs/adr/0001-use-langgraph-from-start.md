# ADR 0001: LangGraph を Phase 1 着手時から採用する

## ステータス
Accepted — 2026-04-25（2026-04-30 文言修正）

## コンテキスト

Ingest パイプラインは以下の特徴を持つ:
- ステージが多い（download → frames → [whisper, yolo, caption] → fuse → embed → store）
- 中盤で並列実行可能（whisper / yolo / caption）
- ステージごとに失敗確率がそれなりに高い（外部LLM呼び出し、GPU OOM 等）
- 一部ステージの再実行コストが高い（Whisper large は数分かかる）

素の Python (asyncio) で書くこともできるが、以下が欲しい:
- **明示的な状態遷移**（可視化できる）
- **チェックポイント機能**（失敗箇所から再開）
- **LangSmith との統合**（LLM 呼び出しトレース）
- **並列ノードの安全な状態マージ**（Reducer）

## 検討した選択肢

### A. 素の asyncio + 自作オーケストレーター
- Pros: 依存が少ない、学習コストゼロ
- Cons: checkpoint / retry / 可視化を全部自作になる。面接で語れる独自性は無い

### B. Prefect / Dagster
- Pros: データパイプライン向けの成熟フレームワーク
- Cons: LLM/エージェントに特化していない。LangSmith 連携が弱い

### C. LangGraph
- Pros: エージェント・LLM 前提設計。StateGraph / Checkpointer / LangSmith 連携が標準。学習価値が高い
- Cons: まだ API 変化が速い。バージョン pin 必須

### D. 最初は素の Python で作り、途中で LangGraph へ移行
- Pros: 移行のビフォーアフターを語れる
- Cons: リファクタコストが高い。中途半端になりやすい

## 決定

**C. LangGraph を Phase 1 着手時から採用する**（= 最初に Ingest を書く瞬間から LangGraph で書く）

milestones.md 初版では D（途中から移行）を想定していたが、
レビューで「3日で全書き換えは非現実的」と指摘を受けたため、最初から LangGraph で書く方針に改めた。

**Phase 0 の範囲外**: Phase 0 はプロジェクト基盤（uv / ruff / docker-compose 等）のみで、
LangGraph の依存追加は **Phase 1 で Ingest を実装する直前** に行う（YAGNI）。
ADR-0007 と整合。

## 影響・トレードオフ

- Phase 1 の学習コストが上がるが、後段での書き換え工数（3日）が不要になり、合計工数は下がる
- LangGraph のバージョンは `langgraph >= 0.2, < 0.3` に pin して破壊的変更を避ける
- LangGraph の学び自体がポートフォリオ価値に直結する（要求スキル「LangGraph マルチエージェント」を直接カバー）

## 将来の再検討トリガー

- LangGraph の API が破壊的に変わり追従コストが重くなった場合
- 並列ノードが 3 つを超えて規模が大きくなり、Airflow / Prefect クラスが必要になった場合

## 改訂履歴

- **2026-04-30**: タイトル・ステータス・決定節の「Phase 0 から採用」→「Phase 1 着手時から採用」に修正。
  Phase 0 範囲レビューで「Phase 0 では LangGraph 依存を入れない（YAGNI、Phase 1 着手時に入れる）」を確認したため。
  決定の本質（Phase 6 で書き換える方式は不採用 / 最初から LangGraph で書く）は不変。
