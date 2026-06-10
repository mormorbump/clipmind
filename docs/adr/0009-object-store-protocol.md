# ADR 0009: 動画・フレームの保存は ObjectStore Protocol で抽象化する

## ステータス
Accepted — 2026-06-10

## コンテキスト

architecture.md §2 で Storage レイヤーは「Qdrant / Postgres / Object Store 抽象」と定義済み。
Phase 1 では実体はローカル FS（`./.data/objects/`）に置くが、Phase 8 以降で MinIO / S3 への
差し替えが視野に入っている。

差し替え時に Ingest ノードや API ハンドラを書き換えるのは避けたい。
**抽象境界（Protocol）を切り、実装を後で差し替えられる**形にする。

## 検討した選択肢

### A. ObjectStore Protocol を切り、LocalFSObjectStore 実装を提供
- Pros: 後で MinIO/S3 差し替えが容易、テストでは InMemoryObjectStore を注入可能
- Cons: Phase 1 時点では「ただの Path 操作」を 1 層ラップするだけで過剰に見える

### B. ベタに `pathlib.Path` を使う
- Pros: 軽量、コードが直接
- Cons: 差し替え時に API/Graph 全体に手が入る

### C. fsspec を採用
- Pros: ローカル / S3 / MinIO / GCS 全部統一インターフェース
- Cons: 依存が重い、学習価値は低め（フレームワーク慣れになるだけ）

## 決定

**A. ObjectStore Protocol + LocalFSObjectStore 実装を採用**

```python
from typing import Protocol, BinaryIO
from pathlib import Path

class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    def url_for(self, key: str) -> str: ...

class LocalFSObjectStore:
    def __init__(self, base_dir: Path, public_url_prefix: str = "/static") -> None:
        self.base_dir = base_dir
        self.public_url_prefix = public_url_prefix
```

- `key` は `videos/<video_id>/original.mp4` や `frames/<video_id>/f_0042.jpg` 形式
- `url_for()` は FastAPI で静的配信するための URL（`/static/...`）
- 将来 MinIO に切替えるときは `MinioObjectStore(ObjectStore)` を追加するだけ

## 影響・トレードオフ

- Phase 1 時点では実質「Path ラッパー」だが、Phase 8 で差し替え時に効果が出る
- フロントエンド配信用 URL の規約は `/static/<key>` で固定（FastAPI の `StaticFiles`）
- Protocol 採用により mypy strict との相性が良い（ABC より型推論しやすい）

## 将来の再検討トリガー

- Phase 8 で MinIO 採用時に Protocol が貧弱だったら拡張（`presigned_url()` 等の追加）
- 大量フレーム保存でローカル FS が遅くなったら MinIO へ Phase 内移行
