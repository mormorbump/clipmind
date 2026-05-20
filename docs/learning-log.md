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
> （後日記入）

### Q2. アーキテクチャの中で一番苦労した点は？
> （後日記入）

### Q3. 技術選定で比較したのは？
> （後日記入）— ADR を参照

### Q4. 精度はどう測りましたか？
> （後日記入）— `docs/evaluation.md` の結果数値を引用

### Q5. コスト試算は？
> （後日記入）— `docs/cost-estimation.md` の実測値

### Q6. 失敗・学びは？
> （後日記入）

### Q7. この先やるなら？
> （後日記入）

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
