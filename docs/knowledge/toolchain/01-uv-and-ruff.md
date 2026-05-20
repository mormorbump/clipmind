# ツールチェーン: uv / ruff / mypy / pre-commit

> 関連: ADR-0007, `docs/quality-assurance.md` §3, Phase 0

## なぜ「ツールチェーン」を Knowledge として残すのか

Python プロジェクトは **同じ目的に道具が複数ある**（パッケージ管理だけで pip / poetry / pdm / hatch / uv）。
選択を毎回やり直すと時間が溶ける。ClipMind では Phase 0 で決め切り、ADR-0007 で固定した。
ここはその **概念と運用** をまとめる。

---

## 1. uv — 「次世代の pip + poetry」

### 1.1 何が速いか
- Rust 製、並列ダウンロード + キャッシュ
- 依存解決アルゴリズムが pip より賢く高速（PubGrub 系）
- 既存比 **10〜100 倍速**（pip / poetry 比）

### 1.2 主要コマンド
```bash
uv init --package --python 3.11 --name <pkg>   # 新規プロジェクト
uv add <pkg>                                    # 依存追加 → pyproject + lock
uv add --dev <pkg>                              # dev グループ
uv sync                                         # lock に従って環境同期
uv run <cmd>                                    # venv 内でコマンド実行
uv lock --upgrade                               # 全依存更新
uv tree                                         # 依存ツリー表示
```

### 1.3 lockfile の運用
- `uv.lock` は **必ずコミット**する
- CI の `setup-uv@v3` は `uv.lock` のハッシュをキャッシュキーにする → コミット忘れで CI cache が常に miss
- マルチ環境（macOS arm64 / linux x64）の wheel を両方 lock するので、CI と本番で差が出にくい

### 1.4 dependency-groups
```toml
[project]
dependencies = ["pydantic>=2"]

[dependency-groups]
dev = ["pytest", "ruff", "mypy"]
```
PEP 735 準拠の新方式。`uv sync --all-extras --dev` で全部入る。

### 1.5 ハマりどころ
- **`uv run` の出力がリダイレクトに混入**: `uv run cmd > file.json` とすると、`Building xxx` などの uv 自体の出力もファイルに入って JSON 破損する。`--quiet` を付けるか stderr に流す
- `uv build` の backend が `uv_build` ではなく `hatchling` のテンプレもある。`uv init --package` で uv_build が選ばれる
- `uv add <pkg>` は最新版を pin する。古いバージョンが必要なら `uv add "pkg>=1.0,<2"`

---

## 2. ruff — lint + format 一体型

### 2.1 何が嬉しいか
- ruff 1 ツールで **black + flake8 + isort + pyupgrade + bugbear** 等を網羅
- Rust 製で爆速（100 倍速級）
- 設定が `pyproject.toml` 集約

### 2.2 ルールセット（ClipMind 採用）
```toml
[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]
```

| プレフィックス | 内容 |
|---|---|
| E | pycodestyle errors |
| F | pyflakes（未使用 import 等） |
| I | isort（import 並び順） |
| N | pep8-naming（クラス名 / 関数名規約） |
| UP | pyupgrade（古い構文を新形式に） |
| B | flake8-bugbear（よくある罠） |
| SIM | flake8-simplify（簡略化提案） |
| RUF | ruff 独自ルール |

### 2.3 日本語コメントへの配慮
RUF001/002/003 は全角文字（`（` / `；` 等）を ambiguous と警告するが、
**日本語ドキュメント前提のプロジェクトでは大量誤検知**になる。

```toml
ignore = ["RUF001", "RUF002", "RUF003"]
```

ClipMind は knowledge / ADR / コメントすべて日本語前提なので無効化（ADR-0007）。

### 2.4 fix / format / check の違い
```bash
uv run ruff check .          # lint（修正なし、終了コードで違反有無）
uv run ruff check --fix .    # 自動修正
uv run ruff format .         # フォーマット（black 相当）
uv run ruff format --check . # フォーマット差分確認のみ
```

pre-commit ではこの順番で:
1. `ruff --fix`（修正可能なものを直す）
2. `ruff-format`（フォーマット適用）

---

## 3. mypy strict — 型チェック

### 3.1 なぜ strict から始めるか
- 後で strict 化すると **無数のエラーが噴出** して心が折れる
- 学習価値最大化のため、Phase 0 から `strict = true`
- Phase 0 はコードが少ない（`config.py` 1 ファイル）なので、strict のコストはほぼゼロ

### 3.2 strict = true で有効になる主なオプション
- `disallow_untyped_defs`: 全関数に型注釈必須
- `disallow_any_generics`: `list` だけはダメ、`list[int]` 必須
- `no_implicit_optional`: `def f(x: int = None)` は `x: int | None` 必須
- `warn_return_any`: `Any` を返したら警告
- `warn_unused_ignores`: 不要な `# type: ignore` を警告

### 3.3 Pydantic v2 mypy plugin
```toml
[tool.mypy]
plugins = ["pydantic.mypy"]
```
これがないと、`BaseModel` のフィールドの型推論がうまく効かない。
ClipMind は Pydantic Settings で `config.py` を書くので必須。

### 3.4 外部ライブラリの型不在
```toml
[[tool.mypy.overrides]]
module = ["faster_whisper", "ultralytics"]
ignore_missing_imports = true
```
型 stub がないライブラリは個別に許可。
Phase 0 では空。Phase 1 以降で必要に応じて追加。

---

## 4. pre-commit — フック設計

### 4.1 順序の意図
```
ruff --fix   →   ruff-format   →   mypy   →   bandit   →   detect-secrets
   ↑              ↑                 ↑           ↑              ↑
 直せるなら直す  整形              型エラー     脆弱性パターン  秘匿情報
```

「修正系を先、検査系を後」が原則。`--fix` の自動修正後に format でズレを直し、その後の検査系で違反を検出する。

### 4.2 bandit vs detect-secrets の役割分担

| ツール | 検出方式 | 例 |
|---|---|---|
| **bandit** | パターン/AST | `exec(user_input)`、`subprocess(shell=True)`、`hashlib.md5()` |
| **detect-secrets** | エントロピー + 既知パターン | `sk-XXXX...` のような API キー、AWS access key |

両者は **重複しない**。bandit は「コードの危険」、detect-secrets は「コミット直前の秘匿情報混入」。
両方必要。

### 4.3 detect-secrets の baseline ファイル
- 初回 `detect-secrets scan > .secrets.baseline` で生成
- 既知の「秘匿情報ではないがエントロピー高い文字列」（CSS のハッシュ等）を baseline に記録
- 以降は baseline と差分があるものだけ検出
- baseline 自身は **コミットする**

**Phase 0 でハマった罠**: `uv run --quiet detect-secrets scan > .secrets.baseline` の `--quiet` を忘れると、
`Building clipmind @ ...` のような uv の出力が先頭に混入して JSON 破損する。
detect-secrets-hook が「Unable to read baseline」と曖昧なエラーを出すので原因特定が遅れる。

→ ✅ **Phase 0 で実践**: 上記症状をデバッグ。`head -c 50 .secrets.baseline | od -c` で先頭バイトを確認するのが原因特定の決め手。

### 4.4 pre-commit install の落とし穴
- `pre-commit install` を忘れると、コミット時にフックが走らない
- `pre-commit run --all-files` は **git に追跡されているファイル** だけ対象（untracked は無視）
- 新規プロジェクトでは最初に `git add -A` してから `pre-commit run` で初回検証

---

## 5. CI（GitHub Actions）

### 5.1 services 機能
GitHub Actions の `services:` で **CI ジョブと並走するコンテナ**を立てられる。

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.12.1
    ports: ["6333:6333"]
```

これで integration test から `http://localhost:6333` で叩ける。
docker-compose を CI で動かす必要がない。

### 5.2 ローカル vs CI の差分（ClipMind）

| サービス | ローカル | CI | 理由 |
|---|---|---|---|
| Qdrant | ✅ | ✅ | 検索テストに必要 |
| Redis | ✅ | ✅ | 会話履歴・キューに必要 |
| Postgres | ✅ | ❌（Phase 0 時点）| Phase 1 で alembic 入るまでスキップ。CI 起動コスト削減 |

**Phase 1 着手時に CI services に Postgres を追加** することを `docs/learning-log.md` の引き継ぎメモに残す。

### 5.3 setup-uv のキャッシュ
```yaml
- uses: astral-sh/setup-uv@v3
  with:
    enable-cache: true
    cache-dependency-glob: "uv.lock"
```
`uv.lock` のハッシュをキーに `~/.cache/uv` をキャッシュ。
2 回目以降の `uv sync` が秒で終わる。

---

## 6. 実装で確認したいこと

- [ ] `uv sync` が成功する（Phase 0 ✅）
- [ ] `uv run ruff check .` が clean（Phase 0 ✅）
- [ ] `uv run mypy src` が strict で clean（Phase 0 ✅、`config.py` で動作確認）
- [ ] `uv run pre-commit run --all-files` が全フック green（Phase 0 ✅、baseline 罠で 1 度詰まった）
- [ ] CI が green（Phase 0、push 時に確認）
- [ ] uv.lock コミット忘れで CI cache miss が起きないか
- [ ] mypy strict で Pydantic v2 が詰まらないか（plugin 効いてれば OK、Phase 0 ✅）

---

## 7. 参考リンク

- uv: https://docs.astral.sh/uv/
- ruff: https://docs.astral.sh/ruff/
- mypy: https://mypy.readthedocs.io/
- Pydantic v2 mypy plugin: https://docs.pydantic.dev/latest/integrations/mypy/
- pre-commit: https://pre-commit.com/
- detect-secrets: https://github.com/Yelp/detect-secrets
- bandit: https://bandit.readthedocs.io/
- ADR-0007: `../adr/0007-toolchain.md`

---

## 実践マーカー

- ✅ Phase 0 で実践（uv init / pyproject.toml / pre-commit / docker-compose / CI 雛形 / 3 サービス healthy 確認）
- 罠 1: detect-secrets baseline 生成時に `uv run --quiet` を付け忘れて JSON 破損
- 罠 2: 日本語コメント前提なら RUF001/002/003 を ignore しないと大量誤検知
- 罠 3: `docker compose up` / `docker compose pull` を **同一イメージで複数並列**に投げると互いをロックして進捗ゼロ。
  「pull プロセスは生きているが output が空」という症状でハマる。`ps aux | grep "docker compose"` で並走数を確認、複数あれば `pkill -9 -f "docker compose"` で全停止 → 1 つだけ実行
- 罠 4: **pytest の `no tests collected` は exit code 5**。ローカルで `uv run pytest` がメッセージ的に green に見えても、`echo $?` で確認すると 5。CI のシェルは `set -e` 付きで non-zero を fail 扱いするため落ちる。Phase 0 のような「テスト未実装フェーズ」でも、最小の smoke test（パッケージ import 確認）を 1 つ置いておくのが定石
