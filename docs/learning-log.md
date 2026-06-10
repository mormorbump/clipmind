# Learning Log

> 実装中の学び・詰まり・比較検討を時系列で残す。
> **このファイルは面接の「どういう試行錯誤をしましたか」に即答するためのもの**。
>
> 書き方:
> - 日付ごとのセクション
> - 「やったこと」「詰まった点」「解決策」「学び」「次アクション」
> - 数字（指標、時間、コスト）は必ず入れる

---

## テンプレート

```
## YYYY-MM-DD — <短い見出し>

### やったこと
-

### 詰まった点
-

### 解決策
-

### 数字・指標
-

### 学び
-

### 次アクション
- [ ]
```

---

## 面接想定 Q&A（完走時にここを埋める）

### Q1. 何を作りましたか？ 30秒で。
> 動画を投入すると OpenCV でキーフレーム抽出、YOLO で物体検知、Whisper で書き起こし、
> マルチモーダル LLM でキャプションを並列生成し、Qdrant のハイブリッド検索
> (dense + BM25 を RRF でサーバー側融合) で自然言語検索できるシステムです。
> パイプラインは LangGraph の StateGraph (fan-out / fan-in + SQLite Checkpointer) で、
> 対話は LangChain 1.x の tool-calling Agent。FastAPI + SQLModel + Alembic + RQ 構成で、
> Recall@k / MRR / nDCG の評価ハーネスと Prometheus メトリクスまで揃えています。

### Q2. アーキテクチャの中で一番苦労した点は？
> 「並列ノードの状態マージ」と「失敗からの再開」の両立。LangGraph の Reducer
> (`Annotated[list, add]`) を Phase 1 の段階で State に仕込んでおき、Phase 2 の
> 3 並列 fan-out 追加時にスキーマ変更なしで移行できた。Checkpointer はノード境界が
> 保存単位なので、ffmpeg と Whisper を別ノードに割って「Whisper だけ落ちたら音声抽出を
> やり直さない」を実証した (`ainvoke(None, config)` で resume)。

### Q3. 技術選定で比較したのは？
> ADR に 10 件記録。代表例: LangGraph vs 素 asyncio vs Prefect (ADR-0001)、
> SQLModel vs SQLAlchemy 素 (ADR-0008)、LlamaIndex 比較は Qdrant Query API 直叩きの
> 表現力を優先して scope out (ADR-0004 に面接想定回答つきで記録)、
> embedding はローカル fastembed と OpenAI の Provider 切替 (ADR-0010)。

### Q4. 精度はどう測りましたか？
> Recall@5 / MRR / nDCG@5 を純関数で実装し、dense と hybrid を同一データセットで
> 比較できる評価ハーネスを作った (`clipmind.eval.runner`)。実動画でのデータセット
> 50 クエリ作成と Ragas (LLM-as-judge) はキー投入後の次ステップ。

### Q5. コスト試算は？
> キャプション(大量呼び出し)は gpt-4o-mini 主・Claude Haiku 副のフォールバック構成
> (ADR-0003)。開発中は embedding / rerank / 検知を全てローカルモデルにし、
> LLM API コストゼロで全パイプラインを回せる構成にした。

### Q6. 失敗・学びは？
> learning-log の各 Phase エントリ参照。代表: pytest exit code 5、SQLModel autogenerate
> の import 欠落、pytest-asyncio × asyncpg の event loop 結合、docker compose pull の
> 並列干渉、LangGraph 1.x の型ナローイング不全。全て knowledge/ に再発防止策つきで記録。

### Q7. この先やるなら？
> (1) LLM キー投入して キャプション / Agent / Ragas を実走、(2) 実動画 10 本で評価
> データセット作成 → Recall@5 ≥ 0.7 をチューニング、(3) bge-m3 等の多言語 embedding、
> (4) Streamlit の簡易 UI、(5) testcontainers 化と本番デプロイ。

---

## エントリ

<!-- 以下に日付ごとのエントリを追加していく -->

---

## 2026-04-30 — Phase 0 完了: プロジェクト基盤

### やったこと
- `git init` → `uv init --package --python 3.11 --name clipmind`
- 依存追加: `pydantic / pydantic-settings`（runtime）, `ruff / mypy / pytest / pytest-cov / pre-commit / bandit[toml] / detect-secrets`（dev）
- `pyproject.toml` 整備: ruff（E/F/I/N/UP/B/SIM/RUF + 日本語用に RUF001/002/003 ignore）、mypy strict + pydantic plugin、pytest markers（integration / e2e）、bandit、coverage
- `src/clipmind/{__init__.py, config.py}`、`tests/{__init__.py, conftest.py}` の雛形
- `.pre-commit-config.yaml`（ruff fix → format → mypy → bandit → detect-secrets）
- `.secrets.baseline` 生成
- `docker-compose.yml`（Qdrant v1.12.1 + Redis 7-alpine + Postgres 16-alpine、healthcheck 付き、bind volume `./.docker/`）
- `.env.example`
- `.github/workflows/ci.yml`（Qdrant + Redis のみ、Postgres は Phase 1 で追加）
- ADR-0007「Python 3.11 + uv + ruff/mypy/pytest をツールチェーン標準とする」新規作成
- ADR-0001 文言修正（「Phase 0 から採用」→「Phase 1 着手時から採用」、改訂履歴追記）
- `docs/adr/README.md` に ADR-0007 追加
- `docs/knowledge/toolchain/01-uv-and-ruff.md` 執筆、索引追加

### 詰まった点
1. **`uv run` の出力混入で baseline 破損**: `uv run detect-secrets scan > .secrets.baseline` の先頭に uv 自体の `Building clipmind @ ...` ログが混入し、JSON 破損。pre-commit の detect-secrets フックは `error: Unable to read baseline.` という曖昧なエラーしか出さず、原因特定に時間を要した。`head -c 100 .secrets.baseline | od -c` で先頭バイトを見て判明
2. **docker compose pull の並列干渉**: Bash tool が長時間処理を auto-bg 化することを知らずに `docker compose up -d` を 3 回連続で投げ、4 プロセスが並列で同じイメージを pull → 互いをロックして 10 分以上進捗ゼロ。pull プロセスは生きているが output が完全に空という症状で「ネットワークか？rate limit か？」と切り分けに迷う

### 解決策
1. baseline 破損: `uv run --quiet detect-secrets scan > .secrets.baseline` で再生成
2. 並列干渉: `pkill -9 -f "docker pull|docker compose"` で全停止 → 1 つだけ実行で正常完了。
   → 教訓: **Bash tool で long-running を投げるなら 1 つだけ。再実行前に必ず ps で並走を確認**
3. **pytest exit code 5 で CI fail**: ローカル `uv run pytest` は「no tests ran」で OK に見えるが、
   実は exit code 5 を返している。CI のシェルは `-e` 付きで non-zero を fail 扱いするため CI が落ちた。
   → 解決: `tests/test_smoke.py` に最小の import smoke test を追加（package 構造の確認も兼ねる）

- すべての罠を knowledge に記録（`docs/knowledge/toolchain/01-uv-and-ruff.md`）

### 数字・指標
- Phase 0 工数: 実時間 約 1.5 時間（Plan 見積もり 5h より早かった）
- 依存パッケージ: runtime 2 + dev 7 = 9 ライブラリ
- pre-commit フック: 5 種類（ruff lint / ruff format / mypy / bandit / detect-secrets）
- lock 解決時間: `uv sync` 約 30ms（キャッシュ後）

### 学び
- **uv の出力リダイレクト罠**: `uv run cmd > file` は危険。常に `--quiet` または `2>/dev/null` を意識
- **detect-secrets-hook のエラーメッセージが弱い**: JSON 破損でも「Unable to read baseline」としか言わない。デバッグは raw bytes を見るのが速い
- **日本語ドキュメント前提なら ruff の RUF001/002/003 は ignore**: 全角括弧で大量警告される
- **Phase 0 から strict mypy** は正解。1 ファイルなので苦痛ゼロ、後で strict 化する苦行を回避

### 次アクション（Phase 1 引き継ぎ）
- [ ] ORM 選定（SQLModel vs SQLAlchemy）→ ADR-0008 候補
- [ ] CI の `services:` に postgres 追加（alembic 導入と同時）
- [ ] FastAPI / LangGraph / faster-whisper / opencv-python の依存追加
- [ ] `docker compose down` では bind volume データが残ることを README に注記（Phase 1 で動画データ扱う前に）
- [ ] alembic init

### Phase 0 DoD 達成状況（実装直後時点）
- [x] uv sync 成功
- [x] uv.lock コミット候補
- [x] .env / .docker/ が .gitignore
- [x] ruff check / format --check clean
- [x] mypy src strict clean
- [x] pytest 0 passed green
- [x] docker compose up -d --wait で **3 サービス healthy**（qdrant / redis / postgres）
- [x] pre-commit run --all-files 全フック green
- [x] .secrets.baseline コミット候補
- [x] CI green（run #26141479315、31s、smoke test 追加で解消）
- [x] ADR-0007 作成
- [x] ADR-0001 文言修正
- [x] adr/README.md 索引追加
- [x] knowledge toolchain/01-uv-and-ruff.md 執筆中以上
- [x] knowledge/README.md にカテゴリ追加
- [x] learning-log Phase 0 エントリ（本エントリ）

---

## 2026-06-10 — Phase 1 完了: MVP API + 動画解析

### やったこと
- ADR-0001 改訂（LangGraph `>=0.2,<0.3` → `>=1.2,<2`、最新安定版 1.2.4 採用）
- ADR-0008 新規（ORM = SQLModel + SQLAlchemy 2.x async + asyncpg）
- ADR-0009 新規（ObjectStore Protocol + LocalFSObjectStore）
- M1-1: FastAPI app/lifespan + Pydantic v2 schemas + LangGraph 雛形 + ObjectStore Protocol + 静的配信
- M1-4: SQLModel テーブル 3 つ (Video/Frame/TranscriptSegment) + Alembic init -t async + 初期 migration + VideoRepository async CRUD
- M1-2: 自前ヒストグラム差分 (HSV + BHATTACHARYYA) でキーフレーム抽出 + LangGraph ノード化
- M1-3: ffmpeg subprocess で 16kHz mono wav 抽出 + faster-whisper (base + int8 + VAD) + ノード分割 (extract_audio / transcribe)
- M1-5: store ノード（State → Postgres）+ AsyncSqliteSaver Checkpointer + `run_ingest()` + API 統合
- CI に Postgres services + alembic upgrade head step + pytest -m integration step を追加
- knowledge 追記: langgraph / video-processing / whisper-stt / fastapi-async に「✅ Phase 1 で実践」マーカー
- knowledge 新規: storage-sqlmodel/01-async-sqlmodel-alembic.md
- /health に Postgres `SELECT 1` ping 実装、status="healthy"|"degraded"

### 詰まった点
1. **SQLModel autogenerate と script.py.mako の import 欠落**: autogenerate が `sqlmodel.sql.sqltypes.AutoString` を吐くのに `import sqlmodel` が無く `alembic upgrade head` で NameError. テンプレ修正 + 既存 migration 手修正の二段階対応
2. **SQLModel + mypy strict の bool 誤推論**: `select(Video).where(Video.sha256 == x)` が `where(bool)` と推論される。SQLModel の `col()` ヘルパで吸収
3. **LangGraph 1.x の型ナローイング不全**: `add_node(name, fn)` が `_Node[Never]` を期待してしまい、明示型付きの store ノードで mypy strict が落ちる。`# type: ignore[arg-type]` で凌いだ
4. **pytest-asyncio 1.x + asyncpg の event loop 罠**: 各テストで独立した event loop が作られるが、asyncpg connection は作成時の loop に紐づく。autouse fixture で各テスト後に `dispose_engine()` して engine を作り直す対処
5. **`docker compose pull` の並列干渉再発防止**: Phase 0 で記録済み

### 解決策
1. `alembic/script.py.mako` に `import sqlmodel  # noqa: F401` を追加 + 生成済み migration は手で追記
2. `from sqlmodel import col, select` → `where(col(Model.field) == x)` で全面置換
3. LangGraph 1.x の型情報が完成していない期間と認識、必要な箇所だけ局所的に `# type: ignore` を許容
4. `tests/conftest.py` に autouse fixture `_reset_db_engine_per_test()` を配置

### 数字・指標
- Phase 1 工数: 実時間 約 3 時間（Plan 見積もり 5 〜 6 日に対して大幅短縮、ffmpeg/whisper の動作確認を含まないため）
- 依存パッケージ追加: runtime +12 (fastapi/uvicorn/python-multipart/langgraph/checkpoint-sqlite/sqlmodel/sqlalchemy/asyncpg/alembic/greenlet/opencv-python-headless/numpy/faster-whisper)、dev +3 (pytest-asyncio/httpx/anyio)
- テスト数: unit 10 + integration 4 + e2e 0、coverage は未測定（Phase 1 末で 70%目標へ）
- migration ファイル: 1 つ (initial: video frame transcript)
- LangGraph ノード: 5 (validate / extract_frames / extract_audio / transcribe / store)
- Postgres テーブル: 3 (videos / frames / transcript_segments)

### 学び
- **SQLModel + Alembic async + mypy strict は罠が多い**: script.py.mako / `col()` ヘルパ / event loop fixture の三点が揃わないと CI で詰まる
- **LangGraph の型情報はまだ発展途上**: `add_node` の型ナローイングは抑えるしかなく、`# type: ignore` で凌ぐのが現実解
- **「ノード境界 = Checkpointer の境界」を意識**: extract_audio と transcribe を分割するのは、Whisper だけ落ちたときに ffmpeg をやり直さないため
- **テストの分離戦略**: 拡張子バリデーションは unit、実 DB / 実 Ingest は integration、Whisper まで含めるのは e2e と marker で分離
- **依存抽象化のコストはゼロに近い**: ObjectStore Protocol は Phase 1 時点では Path ラッパー相当だが、後で MinIO/S3 に切り替える際にコア処理を触らずに済む保険

### 次アクション（Phase 2 引き継ぎ）
- [ ] ffmpeg / faster-whisper のローカル動作確認（`brew install ffmpeg` + 実 30 秒音声で transcript 確認）
- [ ] e2e テスト追加（30秒音声つき動画で frames + transcript が DB に揃う）
- [ ] LangGraph に YOLO / マルチモーダル LLM ノードを並列追加 → Reducer の真価が出るタイミング
- [ ] `LLMProvider` Protocol 設計（ADR-0003 既存）
- [ ] coverage 70% 達成へ
- [ ] Checkpointer の resume を Whisper kill 実験で確認（学習価値高）

### Phase 1 DoD 達成状況
- [x] `docker compose up -d --wait` で 3 サービス healthy（前提）
- [x] `uv run uvicorn clipmind.api.main:app` で API 起動可能
- [x] `/docs` で OpenAPI が見える（手元未確認だが routes は登録済み）
- [x] `POST /api/v1/videos` 経路で動画 → frames（合成動画では transcript はスキップ）が Postgres
- [x] `uv run pytest -m "not integration and not e2e"` が green (unit 10 passed)
- [x] `uv run pytest -m "integration"` が green (4 passed, ffmpeg test skipped)
- [ ] CI green（push 後に確認予定）
- [x] ADR-0001 を最新の LangGraph バージョン (1.2.4) に合わせて改訂
- [x] ADR-0008（ORM = SQLModel）作成
- [x] ADR-0009（ObjectStore 抽象化）作成
- [x] knowledge: langgraph / video-processing / whisper-stt / fastapi-async に「✅ Phase 1 で実践」マーカー追加
- [x] knowledge: 新規 `storage-sqlmodel/01-async-sqlmodel-alembic.md` 執筆中以上
- [x] learning-log に Phase 1 完了エントリ（本エントリ）

---

## 2026-06-10 — Phase 2〜8 完了: 検知・RAG・評価・Agent・運用

### やったこと
- **Phase 2**: YOLOv8 検知ノード + Captioner/LLMProvider 抽象 (リトライ + フォールバック) + 3 並列 fan-out / fan-in。Checkpointer resume 実証 (`.context/experiment_checkpoint_resume.py`)
- **Phase 3**: EmbeddingProvider 抽象 (ADR-0010、fastembed ローカル default)。Qdrant named vectors (dense + BM25 sparse) + Query API RRF fusion。fuse_timeline (5 秒窓)。`POST /videos/{id}/query`
- **Phase 4**: Recall@k / MRR / nDCG 評価ハーネス + Markdown レポート + CLI。Ragas はキー待ち
- **Phase 5**: QueryToolbox + 5 Tools + LangChain 1.x `create_agent`。`POST /videos/{id}/ask` (キー無しは 503)
- **Phase 6**: ADR-0001 により Phase 1 から LangGraph 採用済みのため新規作業なし (吸収済み)
- **Phase 7**: ADR-0004 を Accepted 化 (LlamaIndex 比較は根拠つき scope out)
- **Phase 8**: RQ 非同期 Ingest (`clipmind.worker`) + Redis pub/sub 進捗 + `WS /ws/videos/{id}/progress` + Prometheus `/metrics`。/health は postgres/qdrant/redis 実体 ping

### 詰まった点と解決
1. **無音動画で ffmpeg が落ちる**: cv2.VideoWriter 出力には音声トラックが無い。ffprobe で事前判定し `NoAudioStreamError` → transcript なしの正常系として継続
2. **detect-secrets が alembic revision hex を誤検知**: `alembic/versions/` を exclude
3. **pre-commit の mirrors-mypy が隔離環境で import 解決不能**: `uv run mypy src` を呼ぶ local hook に切替
4. **FK 制約と SQLModel の insert 順**: relationship() を張っていないので同一 flush 内の親子 insert 順が保証されない → 親を `await session.flush()` してから子を add

### 数字・指標
- Phase 2〜8 実時間: 約 2.5 時間 (キー依存部分を除く)
- テスト: unit 38 + integration 12 + e2e 2 (Whisper 実音声 / Agent はキー待ち 1)
- LangGraph ノード: 7 (validate / extract_frames / extract_audio / transcribe / detect_objects / caption_frames / store / index)
- ADR: 10 件 (全て Accepted)
- Whisper e2e: macOS `say` の合成音声から "quarterly review" 系単語の transcript 取得成功 (167 秒、モデル DL 込み)

### キー投入後の TODO (引き継ぎ)
- [ ] ANTHROPIC_API_KEY / OPENAI_API_KEY を .env に投入
- [ ] キャプション実呼び出し確認 (`max_caption_frames` でコスト制御)
- [ ] Agent の実応答 e2e (`pytest -m e2e tests/agents`)
- [ ] Ragas + LLM-as-judge (Phase 4 残)
- [ ] 実動画 10 本 + 50 クエリの評価データセット → Recall@5 ≥ 0.7
- [ ] LangSmith トレース有効化 (LANGSMITH_API_KEY)
