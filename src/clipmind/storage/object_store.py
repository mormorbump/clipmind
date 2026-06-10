"""ObjectStore Protocol と LocalFS 実装.

ADR-0009 に従い、動画ファイル・フレーム画像・音声 wav 等の保存先を抽象化する.
Phase 1 はローカル FS、Phase 8 以降で MinIO / S3 への差し替えを想定.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    """動画・画像・音声を key/value で保存する抽象."""

    async def put(self, key: str, data: bytes) -> str:
        """`data` を `key` に保存し、保存先のキー（or URL）を返す."""
        ...

    async def get(self, key: str) -> bytes:
        """`key` の中身を返す."""
        ...

    async def delete(self, key: str) -> None:
        """`key` を削除する（存在しなくてもエラーにしない）."""
        ...

    def url_for(self, key: str) -> str:
        """フロント / API レスポンスで使う閲覧 URL を返す."""
        ...


class LocalFSObjectStore:
    """ローカルファイルシステム上の Object Store 実装."""

    def __init__(self, base_dir: Path, public_url_prefix: str = "/static") -> None:
        self.base_dir = Path(base_dir)
        self.public_url_prefix = public_url_prefix.rstrip("/")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # トラバーサル防止: 解決後のパスが base_dir 配下にあるか確認
        rel = Path(key.lstrip("/"))
        target = (self.base_dir / rel).resolve()
        base = self.base_dir.resolve()
        if base not in target.parents and target != base:
            msg = f"key escapes base_dir: {key}"
            raise ValueError(msg)
        return target

    async def put(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return key

    async def get(self, key: str) -> bytes:
        path = self._resolve(key)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    def url_for(self, key: str) -> str:
        return f"{self.public_url_prefix}/{key.lstrip('/')}"
