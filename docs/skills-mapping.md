# Skills Mapping — 要求スキル × 実装箇所

> 面接・案件獲得時に「どこで何を経験したか」を即答できるようにするための対応表。

---

## 【必須】スキルのカバー

### 1. LLMを活用したアプリケーションの実装経験

| 実装箇所 | 内容 | 得られる具体経験 |
|---|---|---|
| `src/clipmind/agents/` | Tool-calling エージェントで質問応答 | プロンプト設計、Tool定義、応答フォーマット |
| `src/clipmind/ingest/captioner.py` | Claude Vision で動画フレーム要約 | マルチモーダルプロンプト設計、コスト制御 |
| `src/clipmind/graph/fuse.py` | LLMで時系列要約を再構成 | 長文コンテキスト処理 |
| `docs/adr/0003-multi-llm-provider.md` | Anthropic / OpenAI の両対応 | プロバイダ抽象化、フォールバック設計 |

**面接で話せるネタ**:
- 「Claude Vision の 1M context を使い、30分動画のフレーム群を一度に要約する設計をした」
- 「Haiku で粗処理、Sonnet で精処理のエスカレーション戦略でコストを40%削減した」

---

### 2. LangChain・LlamaIndex 等ライブラリを用いたエージェント開発経験

| 実装箇所 | 内容 | 得られる具体経験 |
|---|---|---|
| `src/clipmind/agents/query_agent.py` | LangChain `create_tool_calling_agent` | エージェント構築の定石 |
| `src/clipmind/tools/` | 6種類の Tool 定義 | Tool 設計、型注釈、エラーハンドリング |
| `src/clipmind/rag/retriever.py` | LlamaIndex の Retriever も実装し比較 | LangChain と LlamaIndex の使い分け |
| `docs/adr/0004-langchain-vs-llamaindex.md` | 比較検討 ADR | 技術選定の説明能力 |

**面接で話せるネタ**:
- 「LangChain は Agent 周りが強く、LlamaIndex は Retriever/Index 周りが強いので、ハイブリッド構成にした」
- 「Tool の粒度を細かくしすぎて Agent が迷子になる失敗をしたので、5〜7個に絞った」

---

### 3. API設計・開発、および外部APIを統合したシステム構築の経験

| 実装箇所 | 内容 | 得られる具体経験 |
|---|---|---|
| `src/clipmind/api/` | FastAPI で REST + WebSocket | OpenAPI 自動生成、async、依存性注入 |
| `docs/api-spec.md` | バージョニング、エラー設計 | RESTful 設計の原則 |
| 外部API: Anthropic | LLM 呼び出し | レート制限、retry 戦略 |
| 外部API: OpenAI | Embedding + フォールバック LLM | マルチプロバイダ対応 |
| 外部API: YouTube Data API v3 | 動画メタデータ取得 | OAuth / API key、quota 管理 |
| 外部API: Cohere Rerank | 再ランキング | オプショナル依存の扱い |

**面接で話せるネタ**:
- 「外部 API は3つ統合している。プロバイダ抽象化で新しい LLM も10分で差し替え可能」
- 「WebSocket で長時間 Ingest の進捗をリアルタイム配信、途中切断も再開対応」

---

## 【歓迎】スキルのカバー

### 4. 映像解析（OpenCV, YOLO等）やマルチモーダルAI

| 実装箇所 | 内容 |
|---|---|
| `src/clipmind/ingest/frames.py` | OpenCV でシーンカット検出、キーフレーム抽出 |
| `src/clipmind/ingest/detector.py` | Ultralytics YOLOv8 で物体検知 |
| `src/clipmind/ingest/transcriber.py` | faster-whisper で字幕抽出 |
| `src/clipmind/ingest/captioner.py` | Claude Vision / GPT-4o でフレームキャプション |

**面接で話せるネタ**:
- 「全フレームを LLM に送るとコストが爆発するので、OpenCV のヒストグラム差分でシーンカットを検出し、代表フレームだけを送る設計にした」
- 「YOLO の検知結果と Whisper の字幕を 5 秒窓で fuse し、時系列の意味単位を作った」

---

### 5. ベクトルデータベース（Pinecone, Milvus等）を用いたRAG

| 実装箇所 | 内容 |
|---|---|
| `src/clipmind/storage/qdrant_client.py` | Qdrant クライアント |
| `src/clipmind/rag/embedder.py` | Embedding 生成（text-embedding-3-small） |
| `src/clipmind/rag/retriever.py` | Dense + Sparse (BM25) ハイブリッド検索 |
| `src/clipmind/rag/reranker.py` | Cohere Rerank / bge-reranker-v2-m3 |
| `docs/evaluation.md` | Recall@k, MRR, Ragas による評価 |

**面接で話せるネタ**:
- 「Dense 単独だと `いつ` のような時間表現に弱いので、BM25 とハイブリッドにして Recall@5 を 0.58→0.78 に改善した」
- 「Chunk サイズを 5s / 15s / 30s で比較実験し、15s 窓が最適だった」

---

### 6. LangGraph 等を用いたマルチエージェント・オーケストレーション

| 実装箇所 | 内容 |
|---|---|
| `src/clipmind/graph/ingest_graph.py` | LangGraph StateGraph 定義 |
| `src/clipmind/graph/state.py` | Annotated + Reducer による並列安全な状態 |
| `src/clipmind/graph/checkpointer.py` | SQLite Checkpointer でリトライ対応 |
| `docs/adr/0001-use-langgraph-from-start.md` | 最初から LangGraph を採用した意思決定 |

**面接で話せるネタ**:
- 「並列ノードで `Annotated[list, operator.add]` の Reducer を正しく設定しないと、片方の結果が上書きされて消える罠があった」
- 「Checkpointer を入れておくと、Whisper が死んでも fuse 以降から再実行できる。運用上の価値を実感した」

---

## 網羅マトリクス

| スキル | 実装ファイル数 | ADR | 評価 | 備考 |
|---|---|---|---|---|
| LLM アプリ実装 | 5+ | ✓ | ✓ | コア機能 |
| LangChain Agent | 3+ | ✓ | - | 対話部 |
| LlamaIndex | 1 | ✓ | - | 比較用 |
| API設計 | 10+ | - | - | FastAPI + WS |
| 外部API統合 | 4種 | - | - | LLM2種 + YT + Cohere |
| OpenCV | 1 | - | - | frames.py |
| YOLO | 1 | - | - | detector.py |
| マルチモーダル | 1 | ✓ | ✓ | captioner.py |
| VectorDB / RAG | 3+ | ✓ | ✓ | retriever/embed/rerank |
| LangGraph | 2+ | ✓ | - | graph/ |

全スキルが「単に触った」ではなく「選定理由・評価・学び」まで残る状態で完走することをゴールとする。
