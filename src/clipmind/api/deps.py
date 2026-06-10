"""FastAPI Depends() 用のファクトリ.

`Depends(get_settings)` などを通じてハンドラに注入する.
テストでは `app.dependency_overrides[get_xxx] = ...` で差し替え可能.
"""

from __future__ import annotations

from functools import lru_cache

from clipmind.config import Settings
from clipmind.config import get_settings as _get_settings
from clipmind.storage.object_store import LocalFSObjectStore, ObjectStore


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings を生成しキャッシュ."""
    return _get_settings()


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    """ObjectStore シングルトン."""
    settings = get_settings()
    return LocalFSObjectStore(base_dir=settings.object_store_dir)
