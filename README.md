# ClipMind

> 動画コンテンツを対話型で検索・質問できるマルチエージェントRAGシステム

動画（ローカルファイル / Creative Commons動画 / YouTube URLオプション対応）を投入すると、
OpenCV によるフレーム抽出、YOLO による物体検知、Whisper による音声書き起こし、
マルチモーダルLLMによるシーン理解を経てベクトルDBに保存し、
「動画の05:23で何が起きた？」「この動画で人物Aが登場した全シーンは？」のように
自然言語で検索・質問できる。

---

## これは何？（学習プロジェクト）

以下の要求スキルを **一つの統合アプリで** カバーすることを目的に設計された個人ポートフォリオ。

### カバーするスキル

**必須**
- LLMアプリケーション実装
- LangChain によるエージェント開発（+ LlamaIndex との比較検証あり）
- FastAPI ベースの API 設計、外部API 統合（Anthropic / OpenAI / YouTube Data API v3）

**歓迎**
- 映像解析: OpenCV によるシーンカット検出、YOLOv8 による物体検知
- マルチモーダルAI: Claude Vision / GPT-4o によるフレームキャプショニング
- ベクトルDB: Qdrant を用いたハイブリッド検索RAG（BM25 + Dense）
- LangGraph: 並列ノード + 状態マージによるマルチエージェント・オーケストレーション

詳細な実装箇所とのマッピング: [docs/skills-mapping.md](docs/skills-mapping.md)

---

## ドキュメント索引

| ドキュメント | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | システム構成、LangGraphノード設計、データフロー |
| [docs/requirements.md](docs/requirements.md) | 機能要件・非機能要件 |
| [docs/api-spec.md](docs/api-spec.md) | REST / WebSocket API仕様 |
| [docs/skills-mapping.md](docs/skills-mapping.md) | 要求スキル → 実装箇所の対応表 |
| [docs/evaluation.md](docs/evaluation.md) | RAG評価戦略（Recall@k, Ragas, LLM-as-judge） |
| [docs/quality-assurance.md](docs/quality-assurance.md) | テスト方針、CI/CD、lint/型チェック |
| [docs/cost-estimation.md](docs/cost-estimation.md) | 1時間動画あたりのAPI/計算コスト試算 |
| [docs/milestones.md](docs/milestones.md) | 実装ロードマップ（現実的な工数見積） |
| [docs/learning-log.md](docs/learning-log.md) | 実装中の学びログ（面接用エピソード化） |
| [docs/adr/](docs/adr/) | アーキテクチャ意思決定記録 |
| [docs/knowledge/](docs/knowledge/) | トピック別の概念ノート（学習用） |

---

## ステータス

**現在: Phase 0〜8 実装済み（LLM API キー依存の機能はキー投入待ち）**

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | 基盤 (uv / ruff / mypy strict / docker-compose / CI) | ✅ |
| 1 | FastAPI + LangGraph Ingest + Postgres (SQLModel + Alembic) | ✅ |
| 2 | YOLO 検知 + マルチモーダルキャプション抽象 + 並列 fan-out | ✅ |
| 3 | Qdrant ハイブリッド検索 (dense + BM25 RRF) | ✅ |
| 4 | Retrieval 評価 (Recall@k / MRR / nDCG) | ✅ (Ragas はキー待ち) |
| 5 | Query Agent (LangChain 1.x create_agent + 5 Tools) | ✅ (実応答はキー待ち) |
| 6 | LangGraph 化 | ✅ Phase 1 から LangGraph で実装済み (ADR-0001) |
| 7 | LlamaIndex 比較 | ✅ scope out を ADR-0004 に記録 |
| 8 | RQ 非同期 Ingest + WebSocket 進捗 + Prometheus | ✅ |
| 9 | UI / デモ | ✅ Streamlit UI (`ui/app.py`) |

## クイックスタート

```bash
# 1. 依存サービス起動 (Qdrant / Redis / Postgres)
docker compose up -d --wait

# 2. Python 環境
uv sync --all-extras --dev

# 3. DB マイグレーション
uv run alembic upgrade head

# 4. API 起動
uv run uvicorn clipmind.api.main:app --reload
# Swagger UI: http://localhost:8000/docs

# 5. 動画を投入 (同期 Ingest: フレーム抽出 + YOLO + Whisper + Qdrant インデックス)
curl -X POST http://localhost:8000/api/v1/videos -F "file=@your_video.mp4"

# 6. 自然言語で検索 (ハイブリッド検索)
curl -X POST http://localhost:8000/api/v1/videos/<video_id>/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "シーンの説明", "mode": "hybrid"}'

# (任意) LLM キーを .env に入れると Agent 質問が有効化
curl -X POST http://localhost:8000/api/v1/videos/<video_id>/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "この動画の要点は？"}'
```

### Web UI (Streamlit)

```bash
# API を起動した状態で:
uv run --group ui streamlit run ui/app.py
# http://localhost:8501
```

サイドバーでバックエンドのヘルス状態と対象動画を選択し、3 タブで操作する:
**📥 取り込み** (アップロード + 進捗バー) / **🔍 検索** (hybrid・dense、キーフレーム画像つき) /
**💬 質問** (Agent チャット。LLM キー未設定時はその旨を表示)。

### 非同期 Ingest (Phase 8)

```bash
# .env で ENABLE_ASYNC_INGEST=true にして、ワーカーを起動
uv run rq worker clipmind-ingest --url redis://localhost:6379/0
# 進捗は WebSocket で: ws://localhost:8000/ws/videos/<video_id>/progress
```

### 開発コマンド

```bash
uv run pytest -m "not integration and not e2e"   # unit
uv run pytest -m integration                      # 要 docker compose
uv run pytest -m e2e                              # Whisper 実行等 (重い)
uv run ruff check . && uv run mypy src            # lint + 型
uv run python -m clipmind.eval.runner --dataset eval/dataset.jsonl  # RAG 評価
```

> **注**: ffmpeg が必要 (`brew install ffmpeg`)。YOLO / Whisper / embedding のモデルは初回実行時に自動ダウンロードされる。

---

## ライセンス / 法的注意

- 本リポジトリのコードは MIT を想定
- **YouTube 動画のダウンロード機能は既定で無効**。YouTube利用規約上、明示的にダウンロードは禁止されているため、本プロジェクトでは「メタデータ取得（YouTube Data API v3 経由）」のみを合法的に利用する
- 動画投入は (a) ローカルファイル、(b) Creative Commons / Public Domain 動画、(c) 自身が権利保有する動画 を前提
- 詳細は [docs/adr/0005-youtube-tos-policy.md](docs/adr/0005-youtube-tos-policy.md)
