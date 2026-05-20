# ClipMind — マイルストーン / 実装ロードマップ

> 工数は「学習を兼ねた個人開発」ベースで、フルタイム換算の日数。
> 片手間（夜+週末）での実際の実暦日は **約2〜3倍** で見積もる。

**総工数: フルタイム換算 約 26 人日 / 実暦 5〜6週間**

---

## Phase 0: プロジェクト基盤（2日）

M0-1. リポジトリ初期化
- `uv init` / `pyproject.toml` 整備
- ruff / mypy / pytest / pre-commit 導入
- GitHub Actions `ci.yml` 雛形

M0-2. docker-compose 設計
- Qdrant, Redis, Postgres のコンテナ定義
- `.env.example` 作成

**完了条件**: `docker compose up` で全依存が起動、`pytest` が空で green。

---

## Phase 1: MVP API + 動画解析（5日）

M1-1. FastAPI スケルトン (1日)
- `/api/v1/videos` POST (ローカルファイル) / GET
- `/health` エンドポイント
- Pydantic v2 スキーマ定義

M1-2. OpenCV フレーム抽出（1日）
- シーンカット検出（ヒストグラム差分）
- Object Store（ローカル FS で代用）に保存

M1-3. faster-whisper 統合（1日）
- CLI で単体動作確認
- API エンドポイントから呼び出し

M1-4. Postgres メタデータ保存（1日）
- SQLModel or SQLAlchemy でモデル定義
- Alembic マイグレーション

M1-5. 最初の通しテスト（1日）
- 30秒動画を投入 → フレーム + 字幕が保存される

**完了条件**: ローカル動画をAPI経由で投入して、フレーム＋字幕が DB に保存できる。

**獲得スキル**: API設計、外部API統合（LLMなし段階）、OpenCV、Whisper

---

## Phase 2: 物体検知 + マルチモーダル（4日）

M2-1. YOLOv8 統合（1日）
- フレームごとの検知
- 結果を Postgres に保存

M2-2. マルチモーダル キャプション（2日）
- GPT-4o-mini / Claude Vision を抽象化する `Captioner` インターフェース
- リトライ・フォールバック戦略
- 部分失敗時の Ingest 継続

M2-3. プロバイダ抽象化（1日）
- `LLMProvider` protocol
- Anthropic / OpenAI 両対応
- 設定ファイルで切り替え

**完了条件**: 1本の動画からフレーム・字幕・物体・キャプションが揃う。

**獲得スキル**: YOLO、マルチモーダル、外部API多重統合

---

## Phase 3: RAG構築（5日）

M3-1. Embedding & Qdrant（2日）
- Qdrant クライアント実装
- Segment 単位でベクトル化して upsert

M3-2. Dense 検索API（1日）
- `/videos/{id}/query` エンドポイント
- 単純な top_k 検索

M3-3. BM25 + ハイブリッド検索（1日）
- Qdrant の sparse vector
- RRF（Reciprocal Rank Fusion）でマージ

M3-4. Rerank 導入（1日）
- Cohere Rerank（外部API）
- bge-reranker（ローカル）の両対応

**完了条件**: 動画に対して自然言語クエリで関連セグメントが返る。

**獲得スキル**: RAG、ベクトルDB、外部API統合（Cohere）

---

## Phase 4: 評価基盤（3日）

M4-1. 評価データセット作成（1日）
- 自作動画 10 本を Ingest
- 50 クエリ × 正解セグメント を人手作成

M4-2. Retrieval 評価スクリプト（1日）
- Recall@k, MRR, nDCG を計算
- CSV/Markdown レポート自動生成

M4-3. Ragas + LLM-as-judge（1日）
- エンドtoエンド評価
- CI で 10 クエリ版を自動実行

**完了条件**: Recall@5 >= 0.7 を達成。評価レポートが自動生成される。

**獲得スキル**: 評価設計、Ragas

---

## Phase 5: LangChain Agent（3日）

M5-1. Tool 定義（1日）
- 6種類の Tool（architecture.md 参照）
- 各 Tool を単体テスト

M5-2. Tool-calling Agent（1日）
- `create_tool_calling_agent`
- Message history + Redis

M5-3. ストリーミング対応（1日）
- WebSocket 経由でトークンストリーミング
- Tool 実行ログもストリーム

**完了条件**: 対話形式で動画について質問でき、引用付き回答が返る。

**獲得スキル**: LangChain Agent

---

## Phase 6: LangGraph 移行（3日）

> **重要**: Phase 1〜5 で書いた同期パイプラインを LangGraph に書き換えるのではなく、
> **Phase 1 から LangGraph で書き始める** のが理想。
> ただし学習順として「素の Python で作る → LangGraph の嬉しさを実感」も価値がある。
> ここでは後者を採用しつつ、移行コストを見積もる。

M6-1. StateGraph 定義 + fan-out/fan-in（1日）
- `Annotated[list, add]` の Reducer 設計
- 既存の Ingest フローを移植

M6-2. SQLite Checkpointer 導入（1日）
- 途中失敗からの再開テスト

M6-3. 並列実行検証・チューニング（1日）
- 3ノード並列の速度測定
- LangSmith でトレース確認

**完了条件**: Ingest パイプラインが LangGraph で動き、再開可能で並列化されている。

**獲得スキル**: LangGraph、分散オーケストレーション

---

## Phase 7: LlamaIndex 比較 + ADR完成（1日）

M7-1. LlamaIndex Retriever の実装（0.5日）
- 既存 Dense 検索の裏側を LlamaIndex に差し替えたバージョン

M7-2. ADR 0004 執筆（0.5日）
- 両者の違い、選定理由を実装した上で記述

**完了条件**: ADR 0004 が完成し、LlamaIndex の動くサンプルがある。

---

## Phase 8: 運用機能（3日）

M8-1. 非同期化（Redis Queue）（1日）
- Ingest を RQ に退避
- WebSocket で進捗通知

M8-2. OpenTelemetry + Prometheus（1日）
- FastAPI instrumentation
- `/metrics` 公開
- LangSmith 連携最終化

M8-3. セキュリティ・本番準備（1日）
- アップロード制限、拡張子チェック
- SSRF 対策

**完了条件**: 長時間 Ingest が WebSocket で進捗を出しつつ走る。メトリクスが取れる。

**獲得スキル**: 非同期処理、observability

---

## Phase 9: 仕上げ（2日）

M9-1. 簡易UI（1日）
- Streamlit か Next.js で最低限の画面
- 動画投入、進捗、チャット

M9-2. ドキュメント＋デモ動画（1日）
- README 完成
- 5分のデモ動画
- `docs/learning-log.md` を面接想定Q&A形式に整理

**完了条件**: 面接でポートフォリオとして見せられる状態。

---

## 合計

| Phase | 内容 | 工数 |
|---|---|---|
| 0 | 基盤 | 2 |
| 1 | MVP API | 5 |
| 2 | 検知+マルチモーダル | 4 |
| 3 | RAG | 5 |
| 4 | 評価 | 3 |
| 5 | LangChain Agent | 3 |
| 6 | LangGraph | 3 |
| 7 | LlamaIndex比較 | 1 |
| 8 | 運用 | 3 |
| 9 | 仕上げ | 2 |
| **合計** | | **31人日 ≒ フルタイム6週間** |

片手間での現実的見通し: **2〜3ヶ月**。

---

## 早期撤退ポイント（スコープ制御）

以下の Phase は MVP と切り離せるので、詰まったら scope out:

- **Phase 7**（LlamaIndex比較）: skip 可。ADR で「検討したが工数の都合で実装見送り」と書けば、むしろ現実的な判断として評価される
- **Phase 8 の OpenTelemetry**: LangSmith だけでも観測性は取れる
- **Phase 9 の UI**: API + curl / httpie でデモでも十分

逆に **絶対に省略してはいけない**:
- Phase 4（評価）: これが無いと「作っただけ」
- Phase 5〜6 のどちらか: エージェント経験はコア要求
- 各 ADR の執筆: 意思決定の言語化能力が差別化ポイント
