# SQLModel + SQLAlchemy 2.x async + Alembic

> 関連: ADR-0008, Phase 1, M1-4

## なぜ「SQLModel」を選んだのか

| | SQLModel | SQLAlchemy 2.x async (素) |
|---|---|---|
| Pydantic 統合 | ✅ 同じクラスで Pydantic v2 + ORM | 自前で変換層 |
| FastAPI 親和 | ✅ FastAPI 作者がメンテ | 自前で BaseModel 並走 |
| Async サポート | ✅ (内部 SQLAlchemy 2.x) | ✅ |
| 表現力 | ◯ (薄い) | ✅ フル |
| Alembic 連携 | ✅ (内部が SQLAlchemy なので素直) | ✅ |

FastAPI + Pydantic v2 が確定しているプロジェクトでは SQLModel が最小摩擦。
複雑な join / hybrid_property が必要になったら同モデルから純 SQLAlchemy に降りられる。

---

## 1. async セッションの基本

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async with SessionMaker() as session:
    session.add(video)
    await session.commit()
    await session.refresh(video)
```

### `expire_on_commit=False` が重要
デフォルトの `expire_on_commit=True` だと commit 後にすべての属性が expired になる。
async の世界では「commit 直後に属性アクセス → lazy load → 別 event loop → 爆発」が起きる。
**async セッションでは expire_on_commit=False が事実上必須**。

### `pool_pre_ping=True`
コネクションプールから取り出した接続が死んでないか SELECT 1 でチェックしてくれる。
docker compose down → up で Postgres を上げ直したときの「初回 query が落ちる」を避ける。

---

## 2. SQLModel + mypy strict の罠

`Video.sha256 == sha` のような比較式が、mypy 視点では `bool` と推論される。
SQLAlchemy では `ColumnElement[bool]` を期待するため strict だと爆発。

```python
# NG: mypy strict で落ちる
stmt = select(Video).where(Video.sha256 == sha)

# OK: SQLModel 提供の col() ヘルパ
from sqlmodel import col, select
stmt = select(Video).where(col(Video.sha256) == sha)
```

`col()` は実体は no-op だが、mypy にカラム型情報を伝える役目。
SQLModel + mypy strict プロジェクトでは **全 `where(Model.col == x)` を `where(col(Model.col) == x)` に**。
Phase 1 (M1-4) で実際に踏んだ罠。

---

## 3. Alembic init -t async

```bash
uv run alembic init -t async alembic
```

これで `alembic/env.py` が **非同期テンプレート**で生成される。
オンラインモードが `asyncio.run(run_async_migrations())` 経由になる。

### env.py に必要な追記

```python
from sqlmodel import SQLModel
from clipmind.storage import models  # noqa: F401  # ←モデル import で metadata 登録
from clipmind.config import get_settings

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = SQLModel.metadata
```

ポイント:
- **モデルファイルを import する** (`from clipmind.storage import models`).
  これを忘れると `SQLModel.metadata` にテーブルが登録されておらず、autogenerate が空っぽ
- `set_main_option("sqlalchemy.url", ...)` で Settings.database_url を ini にオーバーライド
- `alembic.ini` の `prepend_sys_path = . src` に修正 (src layout 対応)

### alembic.ini の plaeholder URL

`sqlalchemy.url = driver://user:pass@localhost/dbname` のままだとパース失敗するので、
有効な構文だがダミーの URL に置き換える:
```ini
sqlalchemy.url = postgresql+asyncpg://_placeholder_
```
実体は env.py が Settings から差し込む。

---

## 4. SQLModel autogenerate と sqlmodel import 罠

`alembic revision --autogenerate` で生成される migration には:

```python
sa.Column('sha256', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
```

のように `sqlmodel.sql.sqltypes.AutoString` が出るが、**migration テンプレート（script.py.mako）には `import sqlmodel` が無い**。
結果 `alembic upgrade head` で `NameError: name 'sqlmodel' is not defined` が出る。

### 対処: テンプレに 1 行追加

`alembic/script.py.mako`:
```python
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (SQLModel が autogenerate で sqlmodel.sql.sqltypes を吐くため)
${imports if imports else ""}
```

これで以降の autogenerate は import 入りで生成される。
**既に生成済みの migration は手で `import sqlmodel` を足す必要がある**ことに注意。

→ ✅ **Phase 1 (M1-4) で実践**: 上記の罠を踏んでテンプレを修正

---

## 5. pytest-asyncio 1.x + asyncpg の event loop 罠

pytest-asyncio 1.x はデフォルトで **各テストごとに独立した event loop** を作る。
一方 asyncpg の Connection は **作成時の event loop に紐づく**。

```
[test_a]
  event_loop_A 作成
  engine = create_async_engine(...)   # asyncpg connection は loop_A 紐付け
  ... test 通過 ...
  event_loop_A 閉じる

[test_b]
  event_loop_B 作成
  engine （まだ生きてる、グローバルキャッシュ）
  connection を使う → loop_A 紐付けなのに loop_B が current → RuntimeError: Event loop is closed
```

### 対処: 各テスト後に engine をリセット

```python
@pytest.fixture(autouse=True)
async def _reset_db_engine_per_test():
    yield
    from clipmind.storage.db import dispose_engine
    await dispose_engine()
```

`dispose_engine()` で `_engine = None` に戻し、次テストで `get_engine()` 呼び出し時に
**新規 event loop に紐づく** engine を作り直す。

別解として `asyncio_default_fixture_loop_scope = "session"` を pyproject に書いて
session 全体で event loop を共有する手もあるが、テスト独立性が下がるので
「engine を毎回作り直す」方が安全。

→ ✅ **Phase 1 (M1-5) で実践**

---

## 6. 実装で確認したいこと

- [x] `alembic init -t async alembic` で非同期テンプレ (Phase 1 M1-4 ✅)
- [x] env.py から `Settings.database_url` を差し込む (Phase 1 ✅)
- [x] `SQLModel.metadata` に登録 → autogenerate が テーブルを検出 (Phase 1 ✅)
- [x] `alembic upgrade head` 後 pg_tables に `videos / frames / transcript_segments` が並ぶ (Phase 1 ✅)
- [x] async CRUD テストが pass (Phase 1 ✅)
- [x] `col()` ヘルパで mypy strict が clean (Phase 1 ✅)
- [x] pytest 内で複数 integration test を流しても event loop で爆発しない (Phase 1 ✅)

---

## 7. 参考リンク

- SQLModel: https://sqlmodel.tiangolo.com/
- SQLAlchemy 2.x async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alembic async: https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- ADR-0008: `../../adr/0008-orm-sqlmodel.md`

---

## 実践マーカー

- ✅ Phase 1 (M1-4) で実践: SQLModel + Alembic async + integration test
- 罠 1: SQLModel autogenerate が `sqlmodel.sql.sqltypes.AutoString` を吐くのに `import sqlmodel` が無い (`script.py.mako` 修正)
- 罠 2: mypy strict が `where(Model.col == x)` を bool 推論 (`col()` ヘルパ必須)
- 罠 3: pytest-asyncio 1.x + asyncpg で event loop が閉じる罠 (autouse fixture で dispose)
- 罠 4: `expire_on_commit` を `False` にしないと commit 後の Pydantic 化で lazy load が爆発
