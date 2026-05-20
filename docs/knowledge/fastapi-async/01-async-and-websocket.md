# FastAPI: async / WebSocket / 依存性注入

> 関連: `docs/architecture.md` §2 Interface, `docs/api-spec.md`, Phase 1 / 8

## なぜ FastAPI か

- **async ネイティブ**: LLM API のような I/O 待ちが多い処理に最適
- **Pydantic v2 統合**: 型安全 + 自動バリデーション + OpenAPI 自動生成
- **WebSocket 標準サポート**: 進捗通知やストリーミング応答に必須
- **依存性注入**: テスタビリティが高い

ClipMind は LLM 呼び出し・DB アクセス・外部 API が並ぶ典型的な I/O bound アプリなので、async + FastAPI が素直な選択。

---

## 1. async の基本と落とし穴

### 1.1 何が嬉しいか

```python
@app.get("/videos/{vid}/query")
async def query(vid: str, q: str):
    embed_task   = embed(q)               # OpenAI 呼び出し
    metadata_task = get_metadata(vid)     # Postgres 読み出し
    embed_vec, meta = await asyncio.gather(embed_task, metadata_task)
    ...
```

両者が **同時並行** に走る。直列だと sum、並列だと max のレイテンシ。
LLM 呼び出しは 1 秒以上かかるので、効果が大きい。

### 1.2 罠 1: sync 関数を async コンテキストで呼ぶ

```python
async def handler():
    result = run_whisper(audio)   # ❌ これが同期で重い場合 event loop ブロック
```

→ 解決:
```python
result = await asyncio.to_thread(run_whisper, audio)
```

または専用 ThreadPoolExecutor を持つ。

### 1.3 罠 2: DB ドライバが sync

- SQLAlchemy 2.x の async サポートは充実してきている
- ただし `psycopg2` は sync。`asyncpg` か `psycopg[async]` を使う
- ORM レベルでは SQLAlchemy `async_session_maker`

### 1.4 罠 3: GIL と CPU bound
- async は I/O bound には効くが、CPU bound（YOLO 推論等）には効かない
- そういう処理は **別プロセス（Redis Queue worker）に逃がす**（architecture.md §2）

---

## 2. Pydantic v2 のリクエスト / レスポンス定義

```python
from pydantic import BaseModel, Field
from typing import Literal

class VideoCreateRequest(BaseModel):
    url: str | None = None
    source_type: Literal["local", "url"] = "local"
    metadata: dict = Field(default_factory=dict)

class VideoCreateResponse(BaseModel):
    video_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    ingest_job_id: str

@app.post("/api/v1/videos", response_model=VideoCreateResponse, status_code=201)
async def create_video(req: VideoCreateRequest) -> VideoCreateResponse:
    ...
```

- Pydantic v2 は v1 と非互換な部分がある（`Config` → `model_config`）
- Pydantic v2 は実装が Rust になり爆速
- `response_model` で出力もバリデーション、`/docs` の Swagger に自動反映

---

## 3. 依存性注入（Depends）

```python
from fastapi import Depends

async def get_qdrant() -> QdrantClient:
    return app.state.qdrant_client

async def require_api_key(x_api_key: str = Header(...)):
    if not is_valid(x_api_key):
        raise HTTPException(401)

@app.post("/api/v1/videos")
async def create(
    req: VideoCreateRequest,
    qdrant: QdrantClient = Depends(get_qdrant),
    _ = Depends(require_api_key),
):
    ...
```

- テスト時に `app.dependency_overrides[get_qdrant] = lambda: fake_qdrant`
- ハンドラを **副作用ゼロのまま** テストできる

---

## 4. WebSocket — 進捗通知 / ストリーミング

### 4.1 Ingest 進捗（push）

```python
@app.websocket("/ws/videos/{video_id}/progress")
async def progress(ws: WebSocket, video_id: str):
    await ws.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"ingest:{video_id}")
    async for msg in pubsub.listen():
        if msg["type"] == "message":
            await ws.send_json(msg["data"])
            if msg["data"].get("stage") in ("completed", "failed"):
                break
    await ws.close()
```

- バックエンド（RQ worker）が Redis pub/sub に push
- FastAPI 側はそれを WebSocket に流すだけ → **ステートレス**
- スケールアウトしてもどの worker が引いても OK

### 4.2 対話（双方向）

```python
@app.websocket("/ws/chat/{session_id}")
async def chat(ws: WebSocket, session_id: str):
    await ws.accept()
    while True:
        msg = await ws.receive_json()
        async for event in agent.astream_events({"input": msg["content"]}, version="v2"):
            await ws.send_json(transform(event))
```

- Tool 呼び出し / トークンストリーム / 引用 を逐次送信
- 切断検出は `WebSocketDisconnect` 例外で

### 4.3 注意点
- TLS 終端で WebSocket を切られないよう、リバースプロキシ（nginx/Caddy）の設定確認
- ハートビート（30 秒ごとに ping）を入れないと中継機にタイムアウトされる

---

## 5. 非同期化（Redis Queue）

API は短時間で 202 を返し、重い処理は worker に回すパターン:

```python
# API
@app.post("/api/v1/videos")
async def create(...):
    job = q.enqueue(run_ingest_pipeline, video_id, ...)
    return {"video_id": video_id, "ingest_job_id": job.id}

# worker.py（別プロセス）
def run_ingest_pipeline(video_id):
    state = build_state(video_id)
    graph.invoke(state)
```

- API がブロックされない
- 失敗時の retry は RQ 標準機能
- 並行 worker 数で throughput をスケール

---

## 6. テスト

```python
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_video():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/api/v1/videos", files={"file": ...})
        assert r.status_code == 201
```

- `httpx.AsyncClient` で in-process テスト（実サーバ不要）
- WebSocket テストは `TestClient.websocket_connect`
- 依存性は `app.dependency_overrides` で差し替え

---

## 7. ハマりどころ

### 7.1 BackgroundTasks vs Queue
- `BackgroundTasks` は同一プロセス内のため、API スケール時に消える
- 重い処理は **必ず外部 Queue（Redis Queue 等）** に出す

### 7.2 ファイルアップロードの大容量
- 2GB を一括メモリに読むと OOM
- `UploadFile.read(chunk_size)` でストリーミング書き込み

### 7.3 CORS / CSRF
- 開発と本番で許可 origin が違う → 環境変数で切替
- Cookie ベース認証なら CSRF トークン必須

### 7.4 SSRF 対策（URL 取り込み）
- ユーザーが任意 URL を投げる API は SSRF 攻撃の温床
- ホストのホワイトリスト + DNS 解決後の IP を再チェック（rebinding 対策）

---

## 8. 実装で確認したいこと

- [ ] async/await でチェーンしたエンドポイントが直列より速い
- [ ] WebSocket で 1 時間 Ingest の進捗が安定して届く
- [ ] dependency_overrides でテストが in-process で走る
- [ ] OpenAPI（`/docs`）が型と一致している

---

## 9. 参考リンク

- FastAPI: https://fastapi.tiangolo.com/
- async tutorial: https://fastapi.tiangolo.com/async/
- WebSocket: https://fastapi.tiangolo.com/advanced/websockets/
- Pydantic v2 migration: https://docs.pydantic.dev/latest/migration/

---

## 実践マーカー

- 未実装（Phase 1 で骨格、Phase 8 で本格化）
