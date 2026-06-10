"""`WS /ws/videos/{video_id}/progress` (M8-1, api-spec.md §3.1).

Redis pub/sub を購読してクライアントへ進捗 JSON を転送する.
接続時に最後のイベント (Redis に保存済み) があればまず送る.
"""

from __future__ import annotations

import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from clipmind.api.deps import get_settings
from clipmind.ingest.progress import channel_for

router = APIRouter()


@router.websocket("/ws/videos/{video_id}/progress")
async def progress_ws(websocket: WebSocket, video_id: str) -> None:
    """Ingest 進捗をストリームする WebSocket."""
    import redis.asyncio as aioredis

    await websocket.accept()
    settings = get_settings()
    client = aioredis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    pubsub = client.pubsub()

    try:
        await pubsub.subscribe(channel_for(video_id))

        # 過去の最新イベントを先に送る (途中接続でも状態が分かる)
        latest = await client.get(f"clipmind:progress-latest:{video_id}")
        if latest:
            await websocket.send_text(latest.decode())
            if json.loads(latest).get("stage") == "completed":
                return

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if message is None:
                # 30 秒イベントが無ければ keepalive ping
                await websocket.send_text(json.dumps({"stage": "keepalive"}))
                continue
            data = message["data"].decode()
            await websocket.send_text(data)
            if json.loads(data).get("stage") == "completed":
                break
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel_for(video_id))
            await pubsub.aclose()
            await client.aclose()
        with contextlib.suppress(Exception):
            await websocket.close()
