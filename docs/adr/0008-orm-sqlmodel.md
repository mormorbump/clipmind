# ADR 0008: ORM は SQLModel + SQLAlchemy 2.x async を採用する

## ステータス
Accepted — 2026-06-10

## コンテキスト

Phase 1 で Postgres にメタデータ (Video / Frame / TranscriptSegment) を永続化する。
FastAPI（Pydantic v2）と LangGraph の State から DB に書き込む構成上、以下が欲しい:

- **Pydantic v2 と親和**（State の TypedDict をそのまま DB レコードに近づけたい）
- **async サポート**（FastAPI のリクエスト・LangGraph のノードが async）
- **マイグレーション機構**（Alembic）
- **薄い**（学習プロジェクトなのでフルスタック ORM は持て余す）

## 検討した選択肢

### A. SQLModel + SQLAlchemy 2.x async
- Pros:
  - Pydantic v2 統合 — `BaseModel` と `table=True` を同居できる
  - FastAPI 親和性 高（FastAPI 作者が SQLModel メンテナ）
  - 内部は SQLAlchemy 2.x なので Alembic がそのまま使える
  - 型推論が効きやすく、`select()` の戻りが正しく推論される
- Cons:
  - SQLAlchemy の高度な機能（hybrid_property、複雑な join）に踏み込むと SQLModel 経由では書きづらい
  - メンテナンス頻度が SQLAlchemy 本体より低い

### B. SQLAlchemy 2.x async（DeclarativeBase 直接）
- Pros: 標準、成熟、全機能利用可能
- Cons: Pydantic との変換層を自分で書く必要、型推論セットアップが重い

### C. Tortoise ORM / Piccolo
- Pros: async ネイティブ
- Cons: エコシステムが小さい、Alembic 相当のマイグレーションが弱い

### D. raw asyncpg + dataclass
- Pros: 最軽量、依存最小
- Cons: マイグレーション・型安全・関係性（FK）全部手作り

## 決定

**A. SQLModel + SQLAlchemy 2.x async（asyncpg ドライバ）を採用**

理由:
- FastAPI + Pydantic v2 が既に確定（pyproject 採用済み）。SQLModel が最小摩擦
- Phase 1 のテーブルは 3 つ（Video / Frame / TranscriptSegment）と単純で SQLModel の表現力で十分
- SQLAlchemy ベースなので、複雑な要件が出たら同モデルから純 SQLAlchemy にダウングレード可能（前方退避）

### 採用バージョン

| パッケージ | pin | 備考 |
|---|---|---|
| `sqlmodel` | `>=0.0.22,<1` | 0.0.x 系だが Pydantic v2 対応で実質安定 |
| `sqlalchemy[asyncio]` | `>=2.0,<3` | 2.x の async API |
| `asyncpg` | `>=0.30,<1` | Postgres 非同期ドライバ |
| `alembic` | `>=1.13,<2` | マイグレーション |

### セッション運用

- `engine = create_async_engine(DATABASE_URL, echo=False)`
- セッションは `async_sessionmaker(engine, expire_on_commit=False)`
- FastAPI 依存性注入で `Depends(get_session)` 経由でハンドラに渡す
- LangGraph ノード内では、Graph 起動時に session factory を State に持たせず、
  ノード関数の引数で外から渡す（テスタビリティ確保）

## 影響・トレードオフ

- SQLAlchemy 2.x async + alembic + asyncpg のセットアップは初回学習コストあり
- Alembic は `alembic init -t async alembic` で非同期テンプレを使う
- `expire_on_commit=False` を忘れると、commit 後に Pydantic 化する際に lazy load で落ちる

## 将来の再検討トリガー

- 複雑な join / window 関数で SQLModel の表現力が不足した場合 → SQLAlchemy 2.x への移行
- パフォーマンス問題が出た場合 → 一部 raw SQL に切替（asyncpg を直接叩く）
