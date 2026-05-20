# ClipMind — API Specification

> FastAPI で実装。実装後は `/docs` (Swagger UI) で最新仕様を参照。本書は設計段階の契約。

---

## 1. 共通仕様

### 1.1 ベース URL
```
http://localhost:8000/api/v1
ws://localhost:8000/ws
```

### 1.2 認証
- 開発: なし（`127.0.0.1` のみ listen）
- 本番: `Authorization: Bearer <API_KEY>` ヘッダー

### 1.3 エラー形式
```json
{
  "error": {
    "code": "VIDEO_NOT_FOUND",
    "message": "Video vid_abc does not exist",
    "trace_id": "ls-trace-xxx"
  }
}
```

### 1.4 ステータスコード
| コード | 意味 |
|---|---|
| 200 | 成功 |
| 201 | 作成成功 |
| 202 | 非同期受付（Ingestジョブ等） |
| 400 | バリデーション失敗 |
| 401 | 認証失敗 |
| 404 | リソース不在 |
| 409 | 冪等性違反（重複投入） |
| 413 | ペイロード過大 |
| 429 | レート制限 |
| 500 | サーバーエラー |
| 503 | 依存サービス不可（Qdrant等） |

---

## 2. REST エンドポイント

### 2.1 動画登録（ファイル）
```
POST /api/v1/videos
Content-Type: multipart/form-data

file: <binary>
metadata: {"title": "My Video", "tags": ["tutorial"]}
```

**201 Created**
```json
{
  "video_id": "vid_abc123",
  "status": "queued",
  "ingest_job_id": "job_xyz",
  "sha256": "e3b0c44...",
  "progress_ws_url": "/ws/videos/vid_abc123/progress"
}
```

---

### 2.2 動画登録（URL）
```
POST /api/v1/videos
Content-Type: application/json

{
  "url": "https://example.com/video.mp4",
  "source_type": "url",
  "metadata": {}
}
```

**注意**: YouTube URL は既定で 400 Bad Request を返す。ダウンロードせず
YouTube Data API でメタデータだけ取得する別エンドポイント `/api/v1/videos/youtube-metadata` を用意する。

---

### 2.3 YouTube メタデータ取得（合法）
```
POST /api/v1/videos/youtube-metadata

{
  "youtube_url": "https://www.youtube.com/watch?v=XXXX"
}
```

**200 OK**
```json
{
  "video_id_youtube": "XXXX",
  "title": "...",
  "description": "...",
  "channel": "...",
  "duration_seconds": 312,
  "captions_available": ["en", "ja"]
}
```

---

### 2.4 動画ステータス取得
```
GET /api/v1/videos/{video_id}
```

**200 OK**
```json
{
  "video_id": "vid_abc123",
  "status": "completed",
  "ingest_progress": 1.0,
  "duration_seconds": 600,
  "frame_count": 145,
  "transcript_language": "en",
  "created_at": "2026-04-25T12:00:00Z"
}
```

`status`: `queued` | `processing` | `completed` | `failed`

---

### 2.5 タイムライン取得
```
GET /api/v1/videos/{video_id}/timeline
```

**200 OK**
```json
{
  "video_id": "vid_abc123",
  "segments": [
    {
      "start_ms": 0,
      "end_ms": 5000,
      "transcript": "Welcome to the Q3 review",
      "objects": ["person", "laptop"],
      "caption": "A presenter stands in front of a slide showing Q3 results",
      "key_frame_url": "/frames/vid_abc123/f_0.jpg"
    }
  ]
}
```

---

### 2.6 動画削除
```
DELETE /api/v1/videos/{video_id}
```

**204 No Content**

Qdrant のベクトル、Postgres のメタデータ、Object Store のフレームを全削除。

---

### 2.7 単発クエリ（非対話）
```
POST /api/v1/videos/{video_id}/query

{
  "query": "プレゼンターがQ3の結果を示したのはいつ？",
  "top_k": 5
}
```

**200 OK**
```json
{
  "answer": "05:20〜05:30 の間で示されました。",
  "citations": [
    {
      "timestamp_ms": 320000,
      "frame_url": "/frames/vid_abc123/f_640.jpg",
      "transcript_excerpt": "...let me show you the Q3 results..."
    }
  ],
  "trace_id": "ls-trace-xxx"
}
```

---

### 2.8 対話セッション作成
```
POST /api/v1/chat/sessions

{
  "video_ids": ["vid_abc", "vid_def"],
  "system_prompt_override": null
}
```

**201 Created**
```json
{
  "session_id": "sess_123",
  "ws_url": "/ws/chat/sess_123"
}
```

---

### 2.9 対話セッション削除
```
DELETE /api/v1/chat/sessions/{session_id}
```

---

### 2.10 評価実行（管理系）
```
POST /api/v1/admin/evaluations/run

{
  "dataset": "default",
  "metrics": ["recall@5", "mrr", "ragas_faithfulness"]
}
```

**202 Accepted**
```json
{
  "evaluation_job_id": "eval_123"
}
```

---

### 2.11 ヘルスチェック
```
GET /health
```

**200 OK**
```json
{
  "status": "healthy",
  "deps": {
    "qdrant": "ok",
    "postgres": "ok",
    "redis": "ok",
    "anthropic": "ok"
  }
}
```

---

### 2.12 メトリクス
```
GET /metrics     # Prometheus exposition format
```

---

## 3. WebSocket エンドポイント

### 3.1 Ingest 進捗
```
WS /ws/videos/{video_id}/progress
```

**サーバー → クライアント**
```json
{"stage": "download",       "progress": 0.10, "message": "downloading..."}
{"stage": "extract_frames", "progress": 0.30, "message": "145 frames extracted"}
{"stage": "transcribe",     "progress": 0.50, "message": "whisper running"}
{"stage": "detect_objects", "progress": 0.60, "message": "YOLO inference"}
{"stage": "caption_frames", "progress": 0.75, "message": "vision LLM"}
{"stage": "fuse",           "progress": 0.85}
{"stage": "embed",          "progress": 0.92}
{"stage": "store",          "progress": 0.98}
{"stage": "completed",      "progress": 1.00, "message": "done"}
```

エラー時:
```json
{"stage": "failed", "error_code": "WHISPER_OOM", "message": "..."}
```

---

### 3.2 対話（ストリーミング）
```
WS /ws/chat/{session_id}
```

**クライアント → サーバー**
```json
{"type": "user_message", "content": "この動画の結論は？"}
```

**サーバー → クライアント**
```json
{"type": "tool_call",      "tool": "hybrid_search", "args": {"query": "結論"}}
{"type": "tool_result",    "tool": "hybrid_search", "result_count": 5}
{"type": "assistant_chunk", "content": "この動画の"}
{"type": "assistant_chunk", "content": "結論は..."}
{"type": "citations",       "items": [...]}
{"type": "done",            "trace_id": "ls-..."}
```

---

## 4. バージョニング

- URL 先頭で `/api/v1/` を明示
- 破壊的変更時は `/api/v2/` を並行稼働
- deprecation ヘッダーで旧版の廃止予定日を通知

---

## 5. レート制限（本番）

| エンドポイント | 制限 |
|---|---|
| `POST /videos` | 10 req/min |
| `POST /chat/sessions/*/messages` | 60 req/min |
| `GET /videos/*` | 300 req/min |

超過時は `429 Too Many Requests` + `Retry-After` ヘッダー。
