"""進捗発行のテスト.

unit: NullProgressPublisher / ステージマップ
integration: Redis pub/sub roundtrip (要 redis)
"""

from __future__ import annotations

import asyncio
import json

import pytest

from clipmind.ingest.progress import (
    STAGE_PROGRESS,
    NullProgressPublisher,
    RedisProgressPublisher,
    channel_for,
)

REDIS_URL = "redis://localhost:6379/0"


async def test_null_publisher_noop() -> None:
    await NullProgressPublisher().publish("vid", "extract_frames")


def test_stage_progress_monotonic() -> None:
    """api-spec §3.1: パイプライン順に進捗が単調増加."""
    order = [
        "validate",
        "extract_frames",
        "extract_audio",
        "transcribe",
        "detect_objects",
        "caption_frames",
        "store",
        "index",
        "completed",
    ]
    values = [STAGE_PROGRESS[s] for s in order]
    assert values == sorted(values)
    assert STAGE_PROGRESS["completed"] == 1.0


@pytest.mark.integration
async def test_redis_publisher_roundtrip() -> None:
    """publish したイベントが pub/sub で届き、latest キーにも残る."""
    import redis.asyncio as aioredis

    publisher = RedisProgressPublisher(REDIS_URL)
    subscriber = aioredis.from_url(REDIS_URL)
    pubsub = subscriber.pubsub()
    video_id = "vid-progress-test"

    try:
        await pubsub.subscribe(channel_for(video_id))
        await asyncio.sleep(0.1)  # subscribe 完了待ち

        await publisher.publish(video_id, "transcribe", message="whisper running")

        message = None
        for _ in range(20):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if message:
                break
        assert message is not None, "no pubsub message received"
        event = json.loads(message["data"])
        assert event["stage"] == "transcribe"
        assert event["progress"] == STAGE_PROGRESS["transcribe"]
        assert event["message"] == "whisper running"

        latest = await subscriber.get(f"clipmind:progress-latest:{video_id}")
        assert latest is not None
        assert json.loads(latest)["stage"] == "transcribe"
    finally:
        await subscriber.delete(f"clipmind:progress-latest:{video_id}")
        await pubsub.unsubscribe(channel_for(video_id))
        await pubsub.aclose()
        await subscriber.aclose()
        await publisher.close()
