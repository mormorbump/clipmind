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


@lru_cache(maxsize=1)
def get_segment_index():  # type: ignore[no-untyped-def]  # 戻り値は SegmentIndex (循環 import 回避で遅延)
    """SegmentIndex シングルトン."""
    from clipmind.rag.factory import build_segment_index

    return build_segment_index(get_settings())
