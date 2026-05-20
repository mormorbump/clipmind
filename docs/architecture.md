# ClipMind — アーキテクチャ

## 1. システム全体図

```
┌──────────────────────────────────────────────────────────────┐
│                        Client (CLI / Web UI)                 │
└──────────────┬──────────────────────────────┬────────────────┘
               │ REST                         │ WebSocket
               ▼                              ▼
┌──────────────────────────────────────────────────────────────┐
│           FastAPI Gateway (Uvicorn, async, Pydantic v2)      │
│  Auth · Rate limit · OpenAPI schema · OpenTelemetry traces   │
└──┬───────────────────────────────────────────────┬───────────┘
   │ submit ingest job                             │ query
   ▼                                               ▼
┌─────────────────────────┐           ┌──────────────────────────┐
│  Redis Queue (RQ)       │           │  Query Agent             │
│  (async workers)        │           │  (LangChain Tool-calling)│
└───────────┬─────────────┘           └──────────┬───────────────┘
            │ run graph                         │  search tools
            ▼                                   ▼
┌─────────────────────────────────┐   ┌──────────────────────────┐
│  LangGraph: Ingest Pipeline     │   │  Hybrid Retriever        │
│  (StateGraph + Checkpointer)    │   │  BM25 + Dense (Qdrant)   │
└──┬──────┬──────┬──────┬─────────┘   └──────────┬───────────────┘
   │      │      │      │                        │
   ▼      ▼      ▼      ▼                        ▼
 yt-dlp OpenCV Whisper YOLO                 Qdrant (vectors)
 (opt)  frames (STT)  (obj)                 Postgres (metadata)
                │                           Object Store (frames)
                ▼
          Claude Vision / GPT-4o-mini (captioning)
                │
                ▼
          Embeddings (OpenAI text-embedding-3-small)
                │
                ▼
          Qdrant + Postgres (persist)

Observability: LangSmith (LLM trace) + OpenTelemetry (app trace) + Prometheus (metrics)
```

---

## 2. レイヤー構造

| レイヤー | 責務 | 主要モジュール |
|---|---|---|
| **Interface** | HTTP/WS受付、認証、入力バリデーション | `src/clipmind/api/` |
| **Orchestration** | LangGraph で Ingest 全体を動かす | `src/clipmind/graph/` |
| **Agents** | LangChain Tool-calling Agent、クエリ処理 | `src/clipmind/agents/` |
| **Tools** | Agent に渡すツール群（検索、フィルタ、要約） | `src/clipmind/tools/` |
| **Ingest** | OpenCV / YOLO / Whisper / yt-dlp の実処理 | `src/clipmind/ingest/` |
| **RAG** | embedding, ハイブリッド検索, リランク | `src/clipmind/rag/` |
| **Storage** | Qdrant / Postgres / Object Store 抽象 | `src/clipmind/storage/` |
| **Config** | 環境変数・モデル切替 | `src/clipmind/config.py` |

---

## 3. LangGraph Ingest Pipeline 詳細

### 3.1 状態定義

並列ノードの結果を安全にマージするため `Annotated[list, operator.add]` で Reducer を指定する。

```python
from typing import Annotated, TypedDict, Literal
from operator import add

class Frame(TypedDict):
    index: int
    timestamp_ms: int
    path: str          # object store key

class TranscriptSegment(TypedDict):
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None

class Detection(TypedDict):
    frame_index: int
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]

class Caption(TypedDict):
    frame_index: int
    text: str
    model: str          # claude-sonnet-4-6 / gpt-4o-mini 等

class IngestState(TypedDict):
    video_id: str
    source: Literal["local", "url", "youtube_metadata"]
    video_path: str
    audio_path: str | None

    # 並列ノードの結果 — Reducer でリスト追記をサポート
    frames:       Annotated[list[Frame], add]
    transcripts:  Annotated[list[TranscriptSegment], add]
    detections:   Annotated[list[Detection], add]
    captions:     Annotated[list[Caption], add]

    # fuse_node の出力
    timeline: list[dict] | None

    errors: Annotated[list[str], add]
    checkpoint_ts: str | None
```

### 3.2 ノードとエッジ

```python
graph = StateGraph(IngestState)

graph.add_node("validate",         validate_input)
graph.add_node("download",         download_video)       # skip if local
graph.add_node("extract_audio",    extract_audio)
graph.add_node("extract_frames",   extract_keyframes)    # scene-cut detection
graph.add_node("transcribe",       whisper_transcribe)   # parallel group A
graph.add_node("detect_objects",   yolo_detect)          # parallel group A
graph.add_node("caption_frames",   multimodal_caption)   # parallel group A
graph.add_node("fuse",             fuse_timeline)        # join
graph.add_node("embed",            embed_segments)
graph.add_node("store",            persist)

graph.add_edge(START, "validate")
graph.add_edge("validate", "download")
graph.add_edge("download", "extract_audio")
graph.add_edge("extract_audio", "extract_frames")

# fan-out (並列)
graph.add_edge("extract_frames", "transcribe")
graph.add_edge("extract_frames", "detect_objects")
graph.add_edge("extract_frames", "caption_frames")

# fan-in: fuse が 3 ノード全ての完了を待つ
graph.add_edge(["transcribe", "detect_objects", "caption_frames"], "fuse")

graph.add_edge("fuse", "embed")
graph.add_edge("embed", "store")
graph.add_edge("store", END)

# SQLite Checkpointer — 任意の時点から再開可能
graph = graph.compile(checkpointer=SqliteSaver.from_conn_string("checkpoints.db"))
```

### 3.3 fuse_node の時系列マージ戦略

並列ノードの結果を「時刻窓」で束ねる。ウィンドウ幅は 5 秒デフォルト（可変）。

```
for window in sliding_windows(duration=5s, stride=5s):
    segment = {
        "start_ms": window.start,
        "end_ms": window.end,
        "transcript": join_text(transcripts in window),
        "objects": unique([d.label for d in detections in window]),
        "captions": [c.text for c in captions where frame in window],
        "key_frame_index": pick_most_informative_frame(...),
    }
```

この segment 単位が RAG の検索単位（chunk）になる。

---

## 4. Query Agent（LangChain）

### 4.1 エージェント構成

- `create_tool_calling_agent` ベース
- LLM: Claude Sonnet 4.6（推論）
- 会話履歴: `RunnableWithMessageHistory` + Redis

### 4.2 ツール

| ツール | 入力 | 出力 | 用途 |
|---|---|---|---|
| `hybrid_search` | query, top_k, video_id? | segments | BM25 + Dense のハイブリッド検索 |
| `filter_by_time` | video_id, start, end | segments | 時刻窓で絞り込み |
| `filter_by_object` | video_id, label, min_conf | segments | YOLOラベル絞り込み |
| `get_frame_image` | video_id, timestamp_ms | image_url | UI表示用フレーム取得 |
| `summarize_segment` | segments | text | 区間横断要約（Sonnet） |
| `get_video_metadata` | video_id | dict | 動画の基本情報 |

### 4.3 応答フォーマット

```json
{
  "answer": "05:20〜05:30 の間で、プレゼンター A がスライド『Q3 Results』を表示しました。",
  "citations": [
    {
      "video_id": "vid_abc",
      "timestamp_ms": 320000,
      "frame_url": "/frames/vid_abc/f_640.jpg",
      "transcript_excerpt": "...let me show you the Q3 results..."
    }
  ],
  "trace_id": "ls-trace-xxx"
}
```

---

## 5. ハイブリッド検索（RAG）

- **Dense**: `text-embedding-3-small`（1536次元、コスト/品質バランス）
- **Sparse (BM25)**: Qdrant の sparse vector 機能を利用
- **Rerank**: 上位 20 件を Cohere Rerank または `bge-reranker-v2-m3`（ローカル）で再ランク → 上位 5 件を LLM へ

`docs/adr/0006-evaluation-strategy.md` で比較評価する。

---

## 6. 外部依存と失敗戦略

| 外部 | 失敗時の挙動 |
|---|---|
| Anthropic API | 指数バックオフ（3回）→ GPT-4o-mini へフォールバック |
| OpenAI API | 同上（逆向き） |
| Qdrant | 起動チェック。失敗時はヘルスチェックで `503` |
| Whisper (local) | GPUなし環境では `base` モデル、ある環境では `large-v3` |
| YouTube Data API | レート制限: 1日10k ユニット。キャッシュ必須 |

---

## 7. 観測性（Observability）

| 対象 | 手段 |
|---|---|
| LLM 呼び出し | LangSmith（LangChain/LangGraphと自動連携） |
| HTTPリクエスト | OpenTelemetry Instrumentation for FastAPI |
| アプリメトリクス | Prometheus `/metrics` エンドポイント |
| エラー | Sentry（オプション） |

主要メトリクス:
- `ingest_duration_seconds`（ヒストグラム、ステージ別ラベル）
- `llm_tokens_total`（counter、プロバイダ/モデル別）
- `rag_search_recall_at_5`（評価バッチから定期投入）

---

## 8. セキュリティ

- アップロード動画のサイズ上限: 2GB
- 拡張子ホワイトリスト: `.mp4 .mov .mkv .webm`
- URL取り込み時の SSRF 対策: ホワイトリスト方式（YouTube / Vimeo / 自ドメインのみ）
- APIキーは全て環境変数 + AWS Parameter Store 想定
