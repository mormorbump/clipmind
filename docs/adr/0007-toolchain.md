# ADR 0007: Python 3.11 + uv + ruff/mypy/pytest をツールチェーン標準とする

## ステータス
Accepted — 2026-04-30

## コンテキスト

Phase 0 でプロジェクト基盤を組むにあたり、以下の選択を **一括で確定** する必要がある。
これらは後から変更すると全モジュールに波及するため、ADR で固定する。

| 項目 | 選択肢 |
|---|---|
| Python バージョン | 3.11 / 3.12 / 3.13 |
| パッケージマネージャ | pip+pip-tools / poetry / hatch / **uv** |
| Linter / Formatter | black + flake8 + isort / **ruff** |
| 型チェック | **mypy** / pyright / pyre |
| テストランナー | **pytest** / unittest |
| pre-commit | **pre-commit** / lefthook / なし |
| セキュリティ | **bandit + detect-secrets** / gitleaks 等 |

`docs/requirements.md` §4.6 と `docs/quality-assurance.md` §3 で方向性は既出だが、
バージョン pin と理由を明文化する。

## 検討した選択肢

### Python バージョン

| 案 | 採否 | 理由 |
|---|---|---|
| 3.11 | **採用** | LTS 安定、faster-whisper / opencv-python 等の依存が確実に対応 |
| 3.12 | 見送り | Apple Silicon の一部 ML 系ライブラリで wheel 未提供のケース |
| 3.13 | 見送り | 2026-04 時点でエコシステム追従が遅れる |

→ `requires-python = ">=3.11,<3.13"` で 3.11 系を pin、3.12 への移行も将来許容。

### パッケージマネージャ

| 案 | 採否 | 理由 |
|---|---|---|
| pip + pip-tools | 不採用 | 速度・lock 体験が劣る |
| poetry | 不採用 | install 時間・lock 解決速度で uv に劣る、CI 連携も uv 公式の方が強い |
| hatch | 不採用 | 新興、エコシステム成熟度 |
| **uv** | **採用** | Rust 製で爆速、lockfile 標準対応、`uv run` で venv 暗黙管理、GitHub Actions 公式 setup-uv あり |

### Linter / Formatter

| 案 | 採否 | 理由 |
|---|---|---|
| black + flake8 + isort | 不採用 | 3 ツールを束ねる手間、起動コスト |
| **ruff** | **採用** | 1 ツールで全部、Rust 製、設定が pyproject.toml 集約 |

ルールセット: `E / F / I / N / UP / B / SIM / RUF`。
日本語ドキュメントの全角文字警告（RUF001/002/003）は無効化。

### 型チェック

| 案 | 採否 | 理由 |
|---|---|---|
| **mypy strict** | **採用** | 標準デファクト、Pydantic v2 mypy plugin が公式提供 |
| pyright | 候補 | 高速だが、Pydantic との連携で mypy plugin の方が深い検査 |

`strict = true` を Phase 0 から有効化。学習価値最大化のため最初から厳密に。

### テスト・pre-commit

- **pytest**: デファクト。`markers` で integration/e2e を分離（CI で `-m "not integration and not e2e"`）
- **pre-commit**: ruff → format → mypy → bandit → detect-secrets の順で固定

### セキュリティ

- **bandit**: コードレベルの脆弱性（hardcoded password、危険な関数）
- **detect-secrets**: コミット直前の API キー等の偶発的混入検出

両者は役割が違う（パターンマッチ vs エントロピー検出）ので併用する。

## 決定

| 項目 | 採用 | バージョン |
|---|---|---|
| Python | 3.11 | `>=3.11,<3.13` |
| パッケージマネージャ | uv | `>=0.11.13` |
| Linter / Formatter | ruff | `>=0.15` |
| 型チェック | mypy strict + pydantic.mypy plugin | `>=1.18` |
| テスト | pytest + pytest-cov | `>=9.0` / `>=7.1` |
| pre-commit フレームワーク | pre-commit | `>=4.6` |
| 脆弱性 | bandit | `>=1.8` |
| 秘匿情報 | detect-secrets | `>=1.5` |

すべて `pyproject.toml` の `[dependency-groups.dev]` と `[tool.*]` に集約。

## 影響・トレードオフ

### 良い影響
- ローカル / CI / pre-commit で同じツール群が走るため、「ローカルでは通るが CI で fail」が起きにくい
- `uv` の lock が CI のキャッシュキーに直結し、CI 高速化
- 学習価値: mypy strict + Pydantic v2 の組み合わせは Python の現代的型エコシステムの実践

### 制約
- uv の lockfile 形式は uv 専用。pip / poetry へ戻すには再 lock が必要（YAGNI、不要時にやる）
- mypy strict は外部ライブラリの型未提供で詰まることがある。`[[tool.mypy.overrides]]` で個別 `ignore_missing_imports` する運用
- 日本語コメント・docstring を多用する方針のため、ruff の RUF001/002/003 を無効化（プロジェクト全体方針）

### コスト
- uv / ruff のリリース速度が速い。`renovate` か手動で月 1 回程度の更新

## 関連

- `docs/requirements.md` §4.6（保守性要件）
- `docs/quality-assurance.md` §2〜5（テスト・lint・CI/CD 方針）
- ADR-0001（LangGraph 採用）
- `.context/phase-0-plan.md`（Phase 0 実装計画、ツールチェーンの設定値根拠）

## 再検討トリガー

- uv が deprecation され、別ツールが事実上の標準になった場合
- Pydantic v3 リリース時に mypy plugin 互換性が崩れた場合
- Python 3.13 移行を本気で検討する時期になった場合（依存ライブラリ全部対応確認後）
