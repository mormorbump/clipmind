# Phase 1 — MVP API + 動画解析 Plan

> 状態: AI レビュー反映済み（v2）
> 想定工数: フルタイム換算 5 日 / 実時間 1〜2 週間

## ゴール（milestones.md より）

**完了条件**: ローカル動画 (30 秒の mp4) を API 経由で投入すると、
**OpenCV でキーフレーム抽出 + faster-whisper で字幕生成** が走り、
**Postgres にメタデータが保存** される。

ただし、ADR-0001 で「Phase 1 着手時から LangGraph で書き始める」と決めているため、
素朴な同期処理ではなく **LangGraph StateGraph 駆動の Ingest パイプライン** として書く。

## ADR-0001 との接合（重要）

| | architecture.md §3 の最終形 | Phase 1 の到達点 |
|---|---|---|
| ノード数 | 9 ノード（validate → download → extract_audio → extract_frames → [transcribe / detect_objects / caption_frames] → fuse → embed → store）| **4 ノード**（validate → extract_audio → extract_frames → transcribe）|
| 並列ノード | 3 ノード (whisper / yolo / caption) | **なし**（Phase 1 は直列、Phase 2 で YOLO 並列追加、Phase 2 末で caption 並列追加） |
| Reducer | `Annotated[list, add]` 多用 | **使う**（後で追加するノードに備えて最初から State に Reducer 付き定義） |
| Checkpointer | SQLite Checkpointer | **使う**（Whisper が死んだら再開できる学習価値が大きい） |
| 出力先 | Qdrant + Postgres + Object Store | **Postgres + Object Store のみ**（Qdrant は Phase 3） |

→ **Phase 1 は「LangGraph の骨格 + 2 つの実ノード + Checkpointer」が肝**。
Phase 2 以降で並列ノードが追加されたとき、Reducer が初めて活きる。

### Phase 1 で Reducer を入れる根拠（セルフレビュー）

knowledge/langgraph/01 §2.4 にあるように、**並列ノードが無く同一キーへの書き込みが無ければ Reducer は不要**。
Phase 1 単体では入れる必要が無いのも事実。それでも入れる理由:

1. **前方互換**: Phase 2 で YOLO/Caption の並列ノードを追加するとき、State スキーマを変更すると Alembic 相当の「過去 checkpoint との互換性問題」が起きる。最初から Reducer 付きで定義していれば、ノード追加だけで済む
2. **学習価値**: ADR-0001 で「Phase 1 から LangGraph で書き始める」と決めている以上、その本質である Reducer の構文に最初から触れておく
3. **コストはほぼゼロ**: `Annotated[list[T], add]` の 1 行追加だけ、可読性も損なわない

これは「**動かすために必要**」ではなく「**前方互換 + 学習**」を理由とする YAGNI 違反すれすれの判断、と Plan で明示する。

## 不可逆な選択（Phase 1 で決める / ADR 化）

| 項目 | 候補 | 決定 | ADR |
|---|---|---|---|
| ORM | SQLModel / SQLAlchemy 2.x async | **SQLModel**（後述） | ADR-0008 候補 |
| 動画ファイル保存抽象 | ローカル FS / MinIO / S3 / 直接ベタ書き | **`ObjectStore` Protocol + LocalFSObjectStore 実装**（Phase 1 は FS のみ、後で MinIO に差し替え可能に） | ADR-0009 候補 |
| LangGraph バージョン | 0.2 / 0.6 系 | **最新の安定版を使う（実装着手時に確認、ADR-0001 を更新）** | ADR-0001 改訂 |
| マイグレーションツール | Alembic（既存方針） | **Alembic** | ADR 不要 |
| 動画 hash | SHA256（streaming） | **SHA256 / 64KB チャンク streaming** | ADR 不要、knowledge 化 |
| FastAPI バージョン | 0.115 系 | 最新の安定版 | ADR 不要 |

### ORM 選定の根拠（ADR-0008 候補）

| 案 | Pros | Cons |
|---|---|---|
| **SQLModel** | Pydantic v2 統合、FastAPI 親和性、薄い、type-safe | SQLAlchemy より一部機能制限、メンテナンス頻度はやや低い |
| SQLAlchemy 2.x async | 標準・成熟・全機能、async サポート充実 | Pydantic との橋渡しを自分で書く必要、学習コスト高 |

→ **個人学習プロジェクト + FastAPI 親和性重視** → SQLModel。
制約に当たったら SQLAlchemy 2.x async に移行する選択肢を残す（モデルは SQLAlchemy ベースなので可能）。

### Object Store 抽象化の根拠（ADR-0009 候補）

architecture.md §2 で Storage レイヤーが「Qdrant / Postgres / Object Store 抽象」と明記。
Phase 1 では実体はローカル FS だが、**Phase 8 以降で S3/MinIO に差し替える可能性**がある。
最初から Protocol を切っておけば、差し替え時にコア処理を触らずに済む。

```python
class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes | BinaryIO) -> str: ...  # 返り値はストア内のキー or URL
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    def url_for(self, key: str) -> str: ...  # フロントから参照する URL

class LocalFSObjectStore(ObjectStore):
    base_dir: Path
    # 実装は base_dir 配下にファイル書き出し、URL は /static/... を返す
```

## 学べる概念（Phase 1 のメイン）

- **LangGraph StateGraph の最小実装** → 既存 knowledge `langgraph/01` の概念を実装で確認
- **LangGraph Checkpointer の運用** → 実際に Whisper を意図的に落として再開を確認
- **FastAPI の async ハンドラ + UploadFile ストリーミング**（2GB 上限、メモリ膨張回避）
- **Pydantic v2 スキーマ** （request / response）
- **SQLModel + Alembic** （非同期セッション、マイグレーション）
- **OpenCV のシーンカット検出 + キーフレーム選別**（histogram diff）
- **faster-whisper の量子化 / VAD filter / segments の構造**
- **ffmpeg による mp4 → 16kHz wav 抽出**（subprocess の安全な使い方）
- **HTTP リクエストとバックグラウンド処理の分離**（202 Accepted パターン、Phase 1 では同期実行も許容）

これらは既存 knowledge の対応トピックに **「✅ Phase 1 で実践」マーカー**を追加する形で記録。

## サブステップ（M1-1 〜 M1-5）

### M1-1: FastAPI スケルトン + LangGraph 雛形 + ObjectStore（実時間 0.5 日）

#### コード追加
```
src/clipmind/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + lifespan
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py        # GET /health
│   │   └── videos.py        # POST/GET /api/v1/videos
│   └── schemas.py           # Pydantic v2 req/res モデル
├── graph/
│   ├── __init__.py
│   ├── state.py             # IngestState (TypedDict + Annotated[list, add])
│   └── ingest_graph.py      # StateGraph 雛形（ノードは未実装）
├── storage/
│   ├── __init__.py
│   └── object_store.py      # Protocol + LocalFSObjectStore
└── ingest/
    └── __init__.py          # 次サブステップで埋める
```

#### 依存追加
```bash
uv add fastapi uvicorn "langgraph>=0.6,<0.7" "langgraph-checkpoint-sqlite>=2"
uv add python-multipart   # UploadFile 用
```

#### エンドポイント
- `GET /health` → api-spec.md §2.11 の契約に従う:
  ```json
  {"status": "healthy",
   "deps": {"postgres": "ok", "redis": "skipped", "qdrant": "skipped", "anthropic": "skipped"}}
  ```
  - **Phase 1 で実体接続するのは Postgres のみ**（M1-4 完了後）
  - redis / qdrant / anthropic は Phase 1 では未使用なので `"skipped"` を返す
  - M1-1 時点では全部 `"skipped"`、M1-4 完了後に postgres を `"ok"` に切り替え
- `POST /api/v1/videos` → multipart で動画受け取り、保存先 URL を返す（実 ingest はまだ）
- `GET /api/v1/videos/{video_id}` → メタデータ返却（DB 接続前は dict ベタ）
- すべて async、Pydantic v2 スキーマで in/out 定義

#### テスト
- `tests/api/test_health.py`: `httpx.AsyncClient` で GET /health が 200
- `tests/api/test_videos.py`: POST で sample 動画（小さい mp4 fixture）を投げて 201 + video_id 取得

#### DoD
- [ ] `uv run uvicorn clipmind.api.main:app` でローカル起動
- [ ] `/docs`（Swagger UI）で API 仕様が見える
- [ ] 上記 2 テストが pass
- [ ] LangGraph の State / Graph 雛形があるが、ノードは空（pass）

---

### M1-2: OpenCV シーンカット検出 + キーフレーム抽出ノード（実時間 1 日）

#### コード追加
- `src/clipmind/ingest/frames.py`: `extract_keyframes(video_path) -> list[Frame]`
- `src/clipmind/graph/nodes/extract_frames.py`: LangGraph ノード
- 既存 ノード雛形を `extract_frames` で埋める

#### 設計
- **自前ヒストグラム差分** で実装
- knowledge `video-processing/01` §1.1（自前）と §1.2（PySceneDetect）の両方が記載されているが、
  **Phase 1 は §1.1 の自前ヒストグラム差分を採用**
- 理由: 学習価値（OpenCV の `calcHist` / `compareHist` に直接触れる）が大きい、依存追加なし
- knowledge §1.2 の記述に「Phase 1 では §1.1 を採用、PySceneDetect は Phase 2 以降の選択肢として残す」を追記

#### テスト
- `tests/fixtures/sample_5s.mp4`（自作 5 秒動画 or ffmpeg で生成）
- `tests/ingest/test_frames.py`: 5 秒動画で N 枚抽出される (N ≧ 1)
- フレーム画像が `ObjectStore` に保存されている

#### DoD
- [ ] sample_5s.mp4 で複数フレームが抽出されて FS に保存される
- [ ] `extract_frames` ノード単体実行が成功
- [ ] knowledge `video-processing/01` に「✅ Phase 1 で実践」マーカー追加

---

### M1-3: ffmpeg 音声抽出 + faster-whisper ノード（実時間 1 日）

#### ノード境界（明示）
architecture.md §3.2 に従い、**`extract_audio` と `transcribe` は別ノード**として実装する。
理由: Checkpointer の checkpoint 単位がノード境界なので、Whisper だけ落ちた場合に
extract_audio をやり直さずに済む（音声抽出も数秒〜数十秒かかる）。

```
extract_frames → extract_audio → transcribe → (Phase 1 末は store へ)
                    ↑                ↑
                checkpoint       checkpoint
```

#### 依存追加
```bash
uv add faster-whisper
# ffmpeg はシステム依存（brew install ffmpeg）
```

#### コード追加
- `src/clipmind/ingest/audio.py`: `extract_audio(video_path) -> audio_path`（ffmpeg 経由）
- `src/clipmind/ingest/transcriber.py`: `transcribe(audio_path) -> list[TranscriptSegment]`
- `src/clipmind/graph/nodes/extract_audio.py`: LangGraph ノード（pure 関数、ingest 層を呼ぶだけ）
- `src/clipmind/graph/nodes/transcribe.py`: LangGraph ノード（同上）

#### 設計
- macOS Apple Silicon: `WhisperModel("base", device="cpu", compute_type="int8")` で確実動作
- GPU 環境を想定しない（Phase 1 は学習用、large-v3 は将来）
- VAD filter ON で高速化
- knowledge `whisper-stt/01` に「✅ Phase 1 で実践」マーカー追加

#### テスト
- `tests/ingest/test_audio.py`: ffmpeg で wav 16kHz mono 抽出
- `tests/ingest/test_transcriber.py`: 5 秒英語動画で「何らかのテキスト」が返る（厳密一致は脆い）

#### DoD
- [ ] 5 秒動画から transcript が取れる
- [ ] `transcribe` ノード単体実行が成功
- [ ] ffmpeg が無い環境で適切に `RuntimeError` 出力

---

### M1-4: Postgres + SQLModel + Alembic（実時間 1 日）

#### 依存追加
```bash
uv add sqlmodel "sqlalchemy[asyncio]>=2" asyncpg alembic
```

#### コード追加
```
src/clipmind/storage/
├── db.py                # engine, session_maker
├── models.py            # SQLModel: Video, Frame, TranscriptSegment
└── repositories/
    ├── __init__.py
    └── video.py         # async CRUD
alembic/
├── env.py               # async 用に書き換え
└── versions/
    └── 001_initial.py
```

#### モデル
```python
class Video(SQLModel, table=True):
    id: UUID = Field(primary_key=True)
    sha256: str = Field(unique=True, index=True)
    source_type: str   # "local"
    duration_seconds: float | None = None
    status: str = "queued"  # queued/processing/completed/failed
    created_at: datetime
    completed_at: datetime | None = None

class Frame(SQLModel, table=True):
    id: UUID = Field(primary_key=True)
    video_id: UUID = Field(foreign_key="video.id", index=True)
    timestamp_ms: int
    object_store_key: str

class TranscriptSegment(SQLModel, table=True):
    id: UUID = Field(primary_key=True)
    video_id: UUID = Field(foreign_key="video.id", index=True)
    start_ms: int
    end_ms: int
    text: str
```

#### Alembic
- `alembic init -t async alembic` で非同期テンプレ
- 初期マイグレーション生成

#### テスト
- testcontainers ではなく、**ローカル docker-compose の postgres** をテストで使う
  - quality-assurance.md §2.2 は testcontainers を要求しているが、**Phase 1 では簡易化**
  - Phase 8（運用機能）で testcontainers 化を検討。learning-log に引き継ぎ
- `tests/storage/test_video_repo.py`: 1 件 insert → select で同じものが返る
- pytest marker `integration` を付ける（CI では postgres services 起動下で実行、ローカルでも実行可）

#### CI 更新
- `.github/workflows/ci.yml` の `services:` に `postgres` を追加（Phase 0 で先送りした項目）
- `DATABASE_URL` 環境変数を CI で設定
- alembic migration を CI で適用してから integration test

#### DoD
- [ ] `alembic upgrade head` でテーブル作成
- [ ] async CRUD テストが pass（integration marker）
- [ ] CI に postgres + alembic + integration test が乗る

---

### M1-5: 通しテスト（実時間 1 日）

#### 統合
- LangGraph `IngestState` に `frames` と `transcripts` が両方溜まる
- `store` ノード（新規）: State を Postgres に書き出す
- `POST /api/v1/videos` から graph を起動（同期、Phase 1 は WebSocket 進捗なし）

#### Checkpointer
- `SqliteSaver.from_conn_string("ingest_checkpoints.db")` を Phase 1 で導入
- Whisper を意図的に raise させて再開できることを学習用に確認

#### テスト
- `tests/e2e/test_ingest_30s.py`: 30 秒の自作 mp4 を POST → frames + transcript が Postgres にある
- `@pytest.mark.e2e`（CI ではスキップ、ローカルで明示実行）

#### DoD
- [ ] 30 秒動画で frames + transcript が DB に揃う
- [ ] graph 実行中に Whisper を kill → resume で続きから完走を学習ログに記録
- [ ] knowledge `langgraph/01` の「実装で確認したいこと」を全てチェック
- [ ] learning-log に Phase 1 完了エントリ

---

## Phase 1 全体の DoD

- [ ] `docker compose up -d --wait` で 3 サービス healthy（前提）
- [ ] `uv run uvicorn clipmind.api.main:app` で API 起動
- [ ] `/docs` で OpenAPI が見える
- [ ] `POST /api/v1/videos` に 30 秒動画 → frames + transcript が Postgres
- [ ] `uv run pytest -m "not integration and not e2e"` が green（unit テスト）
- [ ] `uv run pytest -m "integration"` が green（postgres 起動下）
- [ ] CI green（unit + integration、e2e は skip）
- [ ] ADR-0001 を最新の LangGraph バージョンに合わせて改訂
- [ ] ADR-0008（ORM = SQLModel）作成
- [ ] ADR-0009（ObjectStore 抽象化）作成
- [ ] knowledge: langgraph / video-processing / whisper-stt / fastapi-async に「✅ Phase 1 で実践」マーカー追加
- [ ] knowledge: 新規 `storage-sqlmodel/01-async-sqlmodel-alembic.md` 執筆中以上
- [ ] learning-log に Phase 1 完了エントリ

## リスクと回避策

| リスク | 回避策 |
|---|---|
| Apple Silicon で faster-whisper が遅い | `base` モデル + `int8` で確実動作。large-v3 は Phase 1 で要求しない |
| ffmpeg が未インストール | README に明記、`extract_audio` 起動時に明示的に検出して RuntimeError |
| LangGraph 0.6 系で API が異なる | 着手時に最新公式 doc 確認、ADR-0001 改訂で吸収 |
| async SQLModel + alembic の設定が複雑 | テンプレ動作を Phase 1 の早い段階で確認、詰まったら同期版に倒す逃げ道残す |
| Whisper の hallucination | VAD filter ON、no_speech_prob > 0.6 の segment をフィルタ |
| 大容量動画でメモリ膨張 | UploadFile の chunked read（既存実装パターン） |
| SHA256 計算遅延 | 64KB chunk streaming で I/O bound に倒す |

## このフェーズで作らない / 触らないもの（YAGNI）

- WebSocket 進捗配信（Phase 1 では同期実行で OK、Phase 8 で RQ 移行と同時に WebSocket 化）
- Redis Queue（Phase 8）
- 評価バッチ（Phase 4）
- マルチモーダル LLM / YOLO（Phase 2）
- Qdrant への保存（Phase 3）
- 認証（要件上シングルユーザー前提、本番化フェーズで）

## 工数見積もり

| サブステップ | フルタイム換算 | 実時間 |
|---|---|---|
| M1-1 FastAPI + Graph 雛形 + ObjectStore | 0.5 日 | 半日 |
| M1-2 OpenCV ノード | 1 日 | 1 日 |
| M1-3 ffmpeg + Whisper ノード | 1 日 | 1〜1.5 日 |
| M1-4 Postgres + SQLModel + Alembic | 1 日 | 1.5 日 |
| M1-5 通しテスト + Checkpointer 動作確認 | 1 日 | 1 日 |
| **合計** | **4.5 日** | **5〜6 日** |

milestones.md 見積 5 日とほぼ一致。

## 次フェーズ（Phase 2）への引き継ぎメモ

Phase 2 開始時に必要になる:
- LangGraph に **YOLO ノード** を並列で追加（Reducer が初めて活きる）
- LangGraph に **マルチモーダル LLM ノード** を並列で追加
- `LLMProvider` Protocol 設計（ADR-0003 既存）
- API キーの実利用（`.env` に ANTHROPIC_API_KEY / OPENAI_API_KEY 投入）

## 実装順序（推奨）

1. **【必須前提】** ADR-0001 の LangGraph バージョン確認・改訂 + ADR-0008 / 0009 起案（半日）
   - LangGraph 公式の最新安定版を確認、`>=0.2,<0.3` の pin を更新
   - 改訂前に依存追加するのは ADR 違反 → 順序を守る
2. M1-1 FastAPI + Graph 雛形 + ObjectStore
3. M1-4 Postgres + SQLModel + Alembic（**M1-2 より先**、理由: graph が State を保存する先がないと M1-5 で詰まる）
4. M1-2 OpenCV ノード
5. M1-3 ffmpeg + Whisper ノード（ノードは 2 つに分割: extract_audio / transcribe）
6. M1-5 通しテスト + Checkpointer

> milestones.md の番号順ではなく、**依存関係順** に並べ替え。
> M1-4 を M1-2 より前に持ってくることで、後段の通しテストで詰まらない。

各サブステップ完了時に小さい commit + push。CI green を保つ。
