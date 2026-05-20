# Phase 0 — プロジェクト基盤 Plan

> 状態: AI レビュー反映済み（v2）
> 想定工数: フルタイム換算 2 日 / 実時間 半日〜1 日

## ゴール（milestones.md より）

- `docker compose up` で Qdrant / Redis / Postgres が起動する
- `pytest` が空（テスト 0 個）で green になる
- ruff / mypy / pre-commit が動く
- GitHub Actions の `ci.yml` 雛形がある
- 後続 Phase で「言語・ツール選定」をやり直さなくて済む状態

## 不可逆な選択（Phase 0 で決める / ADR 化する）

| 項目 | 決定 | ADR 候補 |
|---|---|---|
| パッケージマネージャ | **uv**（quality-assurance.md で推奨済み） | ADR-0007（後述） |
| Python バージョン | **3.11+**（requirements.md §4.6 で確定済み） | ADR-0007 に含める |
| Lint/Format | ruff（quality-assurance.md §3.1）| 既存方針なので ADR 不要 |
| 型チェック | mypy strict（quality-assurance.md §3.2）| 既存方針なので ADR 不要 |
| ORM | **Phase 0 では未決定**。Phase 1 の M1-4 で決める | Phase 1 で ADR-0008 |
| マイグレーション | **Alembic**（architecture.md / milestones.md 既出） | ADR 不要 |

→ **新規 ADR-0007「Python 3.11 + uv + ruff/mypy/pytest をツールチェーン標準とする」を作成**。
ORM 選定は Phase 1 まで先送り（YAGNI）。

### ⚠️ ADR-0001 の文言修正もこのフェーズで実施

ADR-0001 は「**LangGraph を Phase 0 から採用**」と書かれているが、milestones.md の意図は
「Phase 1 着手時から LangGraph で書き始める（Phase 6 で書き換える方式は不採用）」。
Phase 0 では **LangGraph の依存追加すらしない**。

→ ADR-0001 のステータス節と決定節の文言を「Phase 1 着手時点から採用」に修正する作業を
ADR-0007 作成と同じ Step 7 で実施。

## 学べる概念（Phase 0 のメイン）

- **uv のロックファイル管理**（pip-tools / poetry との違い、再現性）
- **ruff の設定モデル**（pyproject.toml 集約、fix mode）
- **mypy strict の現実的な運用**（外部ライブラリの型不在問題、`# type: ignore` の節度）
- **pre-commit のフック設計**（ruff format → ruff check → mypy → bandit の順）
- **GitHub Actions のサービスコンテナ機能**（CI 内で Qdrant/Redis を立ち上げる）
- **docker-compose v2 のヘルスチェック・依存関係**（`depends_on: condition: service_healthy`）
- **Pydantic v2 Settings + mypy strict の落とし所**（`SettingsConfigDict` の型推論、`pydantic.mypy` プラグイン）
- **秘匿情報のリポジトリ流出防止**（`.env` / DB volume / `detect-secrets` の使い分け）

これらは `docs/knowledge/` にトピックがまだないので、実装後に追記候補。

## 実装ステップ

### Step 1: ディレクトリ骨格と uv init（30 分）

```
clipmind/
├── pyproject.toml          # uv が生成
├── uv.lock                 # uv が生成 → ★必ずコミット
├── .python-version         # 3.11
├── .gitignore              # Python + uv + IDE + .env + .docker/
├── src/clipmind/
│   ├── __init__.py
│   └── config.py           # 環境変数の Pydantic Settings（雛形のみ）
├── tests/
│   ├── __init__.py
│   └── conftest.py         # 空（Phase 1 で fixtures 追加）
└── README.md               # 既存を維持
```

コマンド:
```bash
uv init --python 3.11
uv add --dev ruff mypy pytest pytest-cov pre-commit bandit detect-secrets
uv add pydantic pydantic-settings
```

**`.gitignore` に必ず含める**:
```
.env
.env.*
!.env.example
.docker/             # docker-compose の bind volume データ
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
*.egg-info/
```

**重要**:
- `uv.lock` は **コミットする**（CI の `enable-cache: true` がこのハッシュをキーにする）
- bind volume（`./.docker/postgres` 等）は `docker compose down -v` では消えない。
  必要なら手動で `rm -rf .docker/`

### Step 2: pyproject.toml 整備（45 分）

```toml
[project]
name = "clipmind"
version = "0.1.0"
requires-python = ">=3.11,<3.13"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]

[tool.mypy]
strict = true
python_version = "3.11"
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
addopts = "-ra -q --strict-markers"
testpaths = ["tests"]
markers = [
    "integration: requires external services (Qdrant, Redis, Postgres)",
    "e2e: hits live LLM APIs",
]
```

Phase 0 では **strict mypy** + **markers 定義** が肝。Phase 1 以降のテスト分離が楽になる。

### Step 3: pre-commit セットアップ（30 分）

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, pydantic-settings]
        args: [--strict]
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.10
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml"]
        additional_dependencies: ["bandit[toml]"]
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]
```

コマンド:
```bash
uv run pre-commit install
uv run detect-secrets scan > .secrets.baseline   # 初回ベースライン
```

**設計意図**:
- `bandit`: コードレベルの脆弱性（`exec()` の使用、ハードコードされたパスワード等）— quality-assurance.md §3.3 で要求
- `detect-secrets`: コミット直前に API キー等の秘匿情報を検出（`.env` に書いてあるはずでも、`.py` に貼り付けた事故を防ぐ）
- 両者は役割が違う（bandit はパターンマッチで脆弱性、detect-secrets はエントロピーで秘匿情報）

### Step 4: docker-compose（45 分）

`docker-compose.yml`:
```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.12.1   # pin
    ports: ["6333:6333", "6334:6334"]
    volumes:
      - ./.docker/qdrant:/qdrant/storage
    healthcheck:
      test: ["CMD-SHELL", "bash -c ':> /dev/tcp/localhost/6333' || exit 1"]
      interval: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - ./.docker/redis:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: clipmind
      POSTGRES_PASSWORD: clipmind
      POSTGRES_DB: clipmind
    ports: ["5432:5432"]
    volumes:
      - ./.docker/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "clipmind"]
      interval: 5s
      retries: 10
```

`.env.example`:
```
# LLM
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# DB
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://clipmind:clipmind@localhost:5432/clipmind

# Observability (任意)
LANGSMITH_API_KEY=
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=clipmind
```

### Step 5: GitHub Actions CI 雛形（30 分）

`.github/workflows/ci.yml`:
```yaml
name: CI
on: [pull_request, push]
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    services:
      qdrant:
        image: qdrant/qdrant:v1.12.1
        ports: ["6333:6333"]
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --all-extras --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -m "not integration and not e2e"
```

**ローカル vs CI の差分**:

| サービス | ローカル（docker-compose） | CI（GitHub Actions） |
|---|---|---|
| Qdrant | ✅ | ✅ |
| Redis | ✅ | ✅ |
| Postgres | ✅ | ❌（Phase 1 で alembic 導入時に追加）|

理由: Phase 0 では DB に書く実コードがない。CI 起動コストを払う価値がない。
Phase 1 で `M1-4 Postgres メタデータ保存` 着手時に CI の `services:` にも追加する。
→ この約束を `## 次フェーズへの引き継ぎメモ` に明示。

### Step 6: 動作確認（30 分）

```bash
# 依存解決
uv sync

# lint
uv run ruff check .
uv run ruff format --check .

# 型（config.py 1 ファイルでも strict が動くか確認）
uv run mypy src

# テスト（空で green を確認）
uv run pytest

# pre-commit
uv run pre-commit run --all-files

# Docker（ローカルは 3 サービス）
docker compose up -d
docker compose ps      # qdrant / redis / postgres が全部 healthy
docker compose down    # コンテナ停止（bind volume のデータは残る）
# 完全リセットしたい時のみ:
# rm -rf .docker/
```

**Pydantic Settings + mypy strict のハマり確認**:
```python
# src/clipmind/config.py の最小例
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    qdrant_url: str = "http://localhost:6333"
```
これに対して `uv run mypy src` が clean になることを確認。
`pydantic.mypy` プラグイン（pyproject で有効化済み）が効いていれば OK。
詰まったら `[[tool.mypy.overrides]]` で個別調整するが、Phase 0 ではここまで。

### Step 7: ADR 整備（45 分）

#### 7.1 ADR-0007 新規作成
`docs/adr/0007-toolchain.md`「Python 3.11 + uv + ruff/mypy/pytest をツールチェーン標準とする」。
理由・代替案（poetry, pip+pip-tools, hatch 等）・トレードオフを書く。

#### 7.2 ADR-0001 文言修正
ステータス節と決定節の「Phase 0 から採用」→「Phase 1 着手時から採用」に修正。
理由を **改訂履歴** として ADR 末尾に追記:
> 2026-04-30: Phase 0 範囲レビューで「Phase 0 では LangGraph 依存を入れない（YAGNI、Phase 1 着手時に入れる）」を確認。
> Phase 0 開始時から **書き始める**わけではないため、文言を「Phase 1 着手時から採用」に修正した。決定の本質は不変。

#### 7.3 ADR README 索引更新
`docs/adr/README.md` に ADR-0007 を追記。

### Step 8: Knowledge トピック追記（30 分）

新規 knowledge トピック `toolchain/` を作成（索引にカテゴリが未存在なので追加）:

- `docs/knowledge/toolchain/01-uv-and-ruff.md`
  - uv のロックファイル運用（pip-tools / poetry との比較）
  - ruff の選んだルール集合（E/F/I/N/UP/B/SIM/RUF）の意図
  - mypy strict の運用ノウハウ
  - pre-commit のフック順序（fix → format → lint → type → security）
  - bandit と detect-secrets の役割分担
  - Pydantic v2 + mypy plugin のハマり

索引（`docs/knowledge/README.md`）も以下を追加:
| 12 | ツールチェーン | [toolchain/01-uv-and-ruff.md](toolchain/01-uv-and-ruff.md) | 執筆中 | 0 | 0007 |

## 完了基準（Phase 0 の Definition of Done）

- [ ] `uv sync` が成功する
- [ ] `uv.lock` がコミットされている
- [ ] `.env` と `.docker/` が `.gitignore` に含まれている
- [ ] `uv run ruff check .` が clean
- [ ] `uv run ruff format --check .` が clean
- [ ] `uv run mypy src` が clean（`config.py` で strict が動くこと）
- [ ] `uv run pytest` が **0 passed** で green（テストはまだない）
- [ ] `docker compose up -d` で **3 サービスが healthy** になる（Postgres 含む、ローカルのみ）
- [ ] `pre-commit run --all-files` が clean（ruff / mypy / bandit / detect-secrets 全部通過）
- [ ] `.secrets.baseline` がコミットされている
- [ ] CI（GitHub Actions）が green（CI では Qdrant + Redis のみ、Postgres なし）
- [ ] ADR-0007 が `docs/adr/` にある
- [ ] ADR-0001 の文言が「Phase 1 着手時から採用」に修正されている
- [ ] `docs/adr/README.md` に ADR-0007 が索引追加されている
- [ ] knowledge `toolchain/01-uv-and-ruff.md` が執筆中以上
- [ ] `docs/knowledge/README.md` に toolchain カテゴリが追加されている
- [ ] `docs/learning-log.md` に Phase 0 完了エントリがある

## リスクと回避策

| リスク | 回避策 |
|---|---|
| mypy strict が外部ライブラリでエラー乱立 | `[[tool.mypy.overrides]]` で個別 ignore_missing_imports |
| pre-commit のバージョン pin が古くなる | `pre-commit autoupdate` を learning-log に記録 |
| Apple Silicon で Postgres / Qdrant の image pull 遅い | platform 明示（linux/arm64）、初回だけ覚悟 |
| docker-compose のヘルスチェック書式バグ | Phase 0 では healthy になる確認だけ。Phase 1 で `depends_on` を厳密化 |

## このフェーズで作らない / 触らないもの（YAGNI）

- ORM のセットアップ（Phase 1 の M1-4）
- FastAPI スケルトン（Phase 1 の M1-1）
- LangGraph / LangChain の依存追加（Phase 1 で追加、Phase 0 ではまだ不要）
- 評価データセット作り（Phase 4）
- LLM プロバイダ抽象（Phase 2）

これらを今やると「動いてないコード」が積み上がるので、各 Phase で必要になったタイミングで追加する。

## 工数見積もり

| Step | 時間 |
|---|---|
| 1. uv init + .gitignore | 0.5h |
| 2. pyproject.toml | 0.75h |
| 3. pre-commit（bandit / detect-secrets 込み）| 0.75h |
| 4. docker-compose | 0.75h |
| 5. CI | 0.5h |
| 6. 動作確認（Pydantic + mypy 確認込み）| 0.5h |
| 7. ADR-0007 + ADR-0001 修正 + 索引 | 0.75h |
| 8. knowledge 追記 + 索引更新 | 0.5h |
| **合計** | **5h（半日強）** |

milestones.md の見積（2 日）に対して短いが、初学者だとデバッグで膨らむ前提で半日 → 1 日見ておく。

## 次フェーズ（Phase 1）への引き継ぎメモ

Phase 1 開始時に必要になる:
- ORM 選定（SQLModel vs SQLAlchemy）→ ADR-0008 候補
- FastAPI / LangGraph / faster-whisper / opencv-python の依存追加
- alembic init
- **CI の `services:` に postgres を追加**（Phase 0 で意図的にスキップしたもの）
- **`docker compose down` では bind volume データが残ることを README に明記**（Phase 1 で動画データを扱う前に注意喚起）
