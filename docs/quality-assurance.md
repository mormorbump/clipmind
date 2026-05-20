# ClipMind — 品質保証（Testing, CI/CD, Lint）

## 1. 方針

AI/ML アプリは「動くけど脆い」状態に陥りやすい。以下を**プロジェクト開始時から導入**して、
後付けになる典型的失敗を避ける。

---

## 2. テスト戦略（ピラミッド）

```
            ┌──────────┐
            │  E2E (5%)│  ← 動画Ingest→Query の通し
         ┌──┴──────────┴──┐
         │ Integration(25%)│  ← API + DB + Qdrant
      ┌──┴─────────────────┴──┐
      │   Unit Tests (70%)    │  ← 純粋ロジック
      └───────────────────────┘
```

### 2.1 Unit Tests (pytest)

**対象**:
- `src/clipmind/rag/` の chunk 分割、embedding 生成の pure function
- `src/clipmind/graph/state.py` の Reducer
- `src/clipmind/ingest/frames.py` のシーンカット検出ロジック（OpenCV呼び出しはモック）

**モック戦略**:
| 依存 | モック方法 |
|---|---|
| LLM (Anthropic/OpenAI) | `responses` ライブラリで HTTP モック、または `LLM` のプロトコル定義 + Fake 実装 |
| Whisper | `pytest.fixture` で固定出力 |
| YOLO | ONNX Runtime を使わず `FakeDetector` |
| Qdrant | 実体は使わず `InMemoryVectorStore` テストダブル |
| OpenCV | ロジック関数は純粋に分離し、画像処理そのものは固定 fixture (10枚の小さい画像) |

**目標カバレッジ**: 70% 以上（`src/clipmind/rag/`, `graph/`, `agents/` は 85% 以上）

### 2.2 Integration Tests

**対象**:
- FastAPI エンドポイント + テスト用 Qdrant (docker-compose で起動)
- LangGraph の fan-out/fan-in が正しく動くか（State マージの検証）

**ツール**: `pytest` + `httpx.AsyncClient` + `testcontainers`

**例**:
```python
@pytest.mark.integration
async def test_ingest_and_query(qdrant_container, redis_container):
    async with AsyncClient(app=app) as c:
        # fixture の 30秒動画を投入
        r = await c.post("/api/v1/videos", files={"file": ...})
        assert r.status_code == 201
        # 処理完了まで WebSocket 経由で待機（timeout 60s）
        ...
        # クエリ
        r = await c.post(f"/api/v1/videos/{vid}/query", json={"query": "..."})
        assert r.status_code == 200
        assert len(r.json()["citations"]) > 0
```

### 2.3 E2E Tests

**対象**:
- `tests/fixtures/sample_30s.mp4` を使った完全な通しシナリオ
- 実際の LLM を叩くため CI では `@pytest.mark.e2e` + 手動トリガーのみ

### 2.4 評価テスト（Regression）

`docs/evaluation.md` の評価バッチを CI で小規模版で実行し、
Recall@5 が基準値を下回ったら fail させる。

```bash
make eval-small  # 10クエリ、3分以内
```

---

## 3. コード品質ツール

### 3.1 Lint / Formatter
- **ruff**: lint + format（Black 互換）
- 設定: `pyproject.toml` に `[tool.ruff]` を集約
- 全ルール: `E`, `F`, `I`, `N`, `UP`, `B`, `SIM`, `RUF`

### 3.2 型チェック
- **mypy** (strict)
- または **pyright**（より高速）
- CI で強制（警告も error 扱い）

### 3.3 セキュリティ
- **bandit**: 一般的な脆弱性
- **pip-audit**: 依存パッケージの CVE

### 3.4 依存管理
- **uv** もしくは **poetry** でロックファイル管理
- Dependabot / Renovate で定期更新 PR

---

## 4. Pre-commit フック

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.x.x
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-requests]
  - repo: https://github.com/pycqa/bandit
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml"]
```

---

## 5. CI/CD（GitHub Actions）

### 5.1 ワークフロー構成

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `ci.yml` | PR, push(main) | lint → type → unit → integration |
| `eval.yml` | PR (optional) | Retrieval 小規模評価（10クエリ） |
| `e2e.yml` | manual dispatch | LLM 本番 API を叩く完全 E2E |
| `release.yml` | tag v*.*.* | Docker build → GHCR push |

### 5.2 ci.yml サンプル
```yaml
name: CI
on: [pull_request, push]
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    services:
      qdrant: { image: qdrant/qdrant, ports: ["6333:6333"] }
      redis: { image: redis:7, ports: ["6379:6379"] }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest tests/unit -x --cov=src
      - run: uv run pytest tests/integration -m integration
```

### 5.3 本番デプロイ

初期フェーズでは **ローカル起動 + docker-compose** のみ。
完走後、以下のいずれかへ拡張:
- **Railway**: 個人学習で安価、簡単
- **Fly.io**: Docker ベース、グローバル展開容易
- **GCP Cloud Run**: GPU不要ならアリ
- GPU 必須の部分（Whisper large / YOLO）は初期はローカルで動かし、本番化は将来課題

---

## 6. ブランチ戦略・コミット

- **Trunk-based**: `main` に小さく PR をマージ
- **Conventional Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- PR テンプレートに「評価指標への影響」欄を設ける（RAG系のリグレッション防止）

---

## 7. ドキュメント品質

- README は常に動く状態（コピペで起動できる）
- ADR は意思決定ごとに必ず残す
- `docs/learning-log.md` は週次更新を目安
- mermaid 図は source を git 管理（レビュー可能に）

---

## 8. 失敗検出のチェックリスト

以下が揃わないと「完成」とみなさない:

- [ ] CI が green
- [ ] カバレッジ >= 70%
- [ ] 評価バッチ（10クエリ）で Recall@5 >= 0.6
- [ ] README の手順通りに他人の環境で `docker compose up` が通る
- [ ] 動画1本 Ingest + 3クエリ の通しデモができる
- [ ] コストログで 1時間動画が $1.0 以下に収まっている
