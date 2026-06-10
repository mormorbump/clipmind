# Knowledge 索引

ClipMind を作る過程で身につけるべき「概念」を、トピック別に集約するための索引。
時系列ではなく **概念単位** で整理する。同じトピックの学びは同じファイルに追記していく。

> **使い方**
> - 設計フェーズで分かっている内容は最初から骨組みとして記述してある
> - 実装中に得た知見は対応するトピックファイルに追記する
> - 「✅ Phase X-Y で実践」マーカーで実装と概念を紐づける
> - 索引（このファイル）は実装が進むたびに状態を更新する

---

## トピック一覧

| # | トピック | ファイル | 状態 | 関連 Phase | 関連 ADR |
|---|---|---|---|---|---|
| 1 | LangGraph (基礎) | [langgraph/01-stategraph-and-reducer.md](langgraph/01-stategraph-and-reducer.md) | 執筆中 | 1, 6 | 0001 |
| 1.1 | LangGraph (使い分け) | [langgraph/02-when-to-use-stategraph.md](langgraph/02-when-to-use-stategraph.md) | 執筆中 | 1, 5 | 0001 |
| 2 | LangChain Agents | [langchain-agents/01-tool-calling.md](langchain-agents/01-tool-calling.md) | 執筆中 | 5 | 0004 |
| 3 | RAG（検索戦略） | [rag/01-hybrid-search.md](rag/01-hybrid-search.md) | 執筆中 | 3 | 0006 |
| 4 | Vector DB（Qdrant） | [vector-db/01-qdrant-basics.md](vector-db/01-qdrant-basics.md) | 執筆中 | 3 | 0002 |
| 5 | マルチモーダルLLM | [multimodal-llm/01-vision-captioning.md](multimodal-llm/01-vision-captioning.md) | 執筆中 | 2 | 0003 |
| 6 | 動画前処理（OpenCV / YOLO） | [video-processing/01-frames-and-detection.md](video-processing/01-frames-and-detection.md) | 執筆中 | 1, 2 | - |
| 7 | 音声認識（Whisper） | [whisper-stt/01-transcription.md](whisper-stt/01-transcription.md) | 執筆中 | 1 | - |
| 8 | 評価（RAG Evaluation） | [evaluation/01-three-layer-evaluation.md](evaluation/01-three-layer-evaluation.md) | 執筆中 | 4 | 0006 |
| 9 | 観測性 | [observability/01-langsmith-otel-prometheus.md](observability/01-langsmith-otel-prometheus.md) | 執筆中 | 8 | - |
| 10 | LLM プロバイダ抽象 | [llm-provider/01-abstraction-and-fallback.md](llm-provider/01-abstraction-and-fallback.md) | 執筆中 | 2 | 0003 |
| 11 | FastAPI / async / WebSocket | [fastapi-async/01-async-and-websocket.md](fastapi-async/01-async-and-websocket.md) | 執筆中 | 1, 8 | - |
| 12 | ツールチェーン（uv / ruff / mypy / pre-commit）| [toolchain/01-uv-and-ruff.md](toolchain/01-uv-and-ruff.md) | 執筆中 | 0 | 0007 |
| 13 | SQLModel / SQLAlchemy async / Alembic | [storage-sqlmodel/01-async-sqlmodel-alembic.md](storage-sqlmodel/01-async-sqlmodel-alembic.md) | 執筆中 | 1 | 0008 |

## 状態の凡例

- **未着手**: ファイル未作成 or プレースホルダのみ
- **執筆中**: 設計から得られる概念は記述済み、実装で追記する余地あり
- **✅完了**: 主要概念を網羅し、実装で実践済み

---

## 設計ドキュメントとの関係

knowledge は「**概念**」、設計ドキュメントは「**この案件での具体決定**」。
両者は補完関係にある。

| 場所 | 役割 |
|---|---|
| `docs/architecture.md` | システム構成（このプロジェクトでの実装） |
| `docs/adr/` | 不可逆な意思決定の記録 |
| `docs/knowledge/` ← ここ | 概念・仕組み・他案件にも転用可能な学び |
| `docs/learning-log.md` | 時系列の試行錯誤・面接想定エピソード |

---

## 学習の進め方（推奨）

1. Phase 開始前に該当 knowledge を読み返す（または骨組みを書く）
2. 実装中に「これは概念として残すべき」と気づいたらメモ
3. Phase 完了時に knowledge に追記、状態を更新
4. 索引のマーカーを更新（`未着手 → 執筆中 → ✅完了`）

phased-learning-build スキル（`/phased-learning-build`）でループを回すと、
この更新作業が自動で進む。
