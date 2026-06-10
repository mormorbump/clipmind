"""Ingest 進捗の発行 / 購読 (M8-1, api-spec.md §3.1).

Redis pub/sub で `clipmind:progress:{video_id}` チャネルに JSON を流す.
WebSocket エンドポイントが購読してクライアントへ転送する.
Redis が無い環境では NullProgressPublisher が黙って捨てる.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

# api-spec.md §3.1 のステージ進捗マップ
STAGE_PROGRESS: dict[str, float] = {
    "validate": 0.05,
    "extract_frames": 0.30,
    "extract_audio": 0.40,
    "transcribe": 0.55,
    "detect_objects": 0.65,
    "caption_frames": 0.75,
    "store": 0.90,
    "index": 0.95,
    "completed": 1.00,
}


def channel_for(video_id: str) -> str:
    """video_id ごとの pub/sub チャネル名."""
    return f"clipmind:progress:{video_id}"


@runtime_checkable
class ProgressPublisher(Protocol):
    """進捗イベントの発行抽象."""

    async def publish(self, video_id: str, stage: str, **extra: Any) -> None:
        """1 イベントを発行する."""
        ...


class NullProgressPublisher:
    """進捗を捨てる (同期実行・テスト用)."""

    async def publish(self, video_id: str, stage: str, **extra: Any) -> None:
        return None


class RedisProgressPublisher:
    """Redis pub/sub への進捗発行."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client: Any = None

    async def _redis(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self.redis_url)  # type: ignore[no-untyped-call]
        return self._client

    async def publish(self, video_id: str, stage: str, **extra: Any) -> None:
        event = {
            "stage": stage,
            "progress": STAGE_PROGRESS.get(stage, 0.0),
            **extra,
        }
        client = await self._redis()
        # 切断中の WS クライアントが後から最新状態を取れるよう、最後のイベントも保存
        await client.set(f"clipmind:progress-latest:{video_id}", json.dumps(event), ex=3600)
        await client.publish(channel_for(video_id), json.dumps(event))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
