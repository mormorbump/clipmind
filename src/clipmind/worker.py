"""RQ ワーカー用の Ingest ジョブ (M8-1).

API プロセスから `Queue.enqueue("clipmind.worker.ingest_job", ...)` で投入し、
別プロセスの RQ ワーカーが実行する:

    uv run rq worker clipmind-ingest --url redis://localhost:6379/0

RQ は同期関数しか実行できないので、内部で asyncio.run する.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

QUEUE_NAME = "clipmind-ingest"


def ingest_job(video_id: str, object_store_key: str) -> dict[str, object]:
    """RQ ジョブ本体. ワーカープロセスで依存を組み立てて run_ingest を回す."""
    from clipmind.config import get_settings
    from clipmind.graph.runner import run_ingest
    from clipmind.ingest.progress import RedisProgressPublisher
    from clipmind.llm.factory import build_captioner
    from clipmind.rag.factory import build_segment_index
    from clipmind.storage.db import dispose_engine, get_session_maker
    from clipmind.storage.object_store import LocalFSObjectStore

    settings = get_settings()
    object_store = LocalFSObjectStore(base_dir=settings.object_store_dir)
    progress = RedisProgressPublisher(settings.redis_url)

    async def _run() -> dict[str, object]:
        try:
            state = await run_ingest(
                video_id=video_id,
                video_path=Path(settings.object_store_dir / object_store_key),
                object_store=object_store,
                audio_dir=settings.data_dir / "audio",
                checkpoint_db_path=settings.checkpoint_db_path,
                session_maker=get_session_maker(),
                captioner=build_captioner(settings),
                segment_index=build_segment_index(settings) if settings.enable_indexing else None,
                progress=progress,
                whisper_model_size=settings.whisper_model_size,
                enable_detection=settings.enable_detection,
                max_caption_frames=settings.max_caption_frames,
            )
            return {"errors": list(state.get("errors", []))}
        finally:
            await progress.close()
            await dispose_engine()

    return asyncio.run(_run())


def enqueue_ingest(redis_url: str, video_id: str, object_store_key: str) -> str:
    """API 側から Ingest ジョブを投入する. 返り値は RQ job id."""
    from redis import Redis
    from rq import Queue

    queue = Queue(QUEUE_NAME, connection=Redis.from_url(redis_url))
    job = queue.enqueue(
        "clipmind.worker.ingest_job",
        video_id,
        object_store_key,
        job_timeout=60 * 60,  # 長時間動画を想定して 1h
    )
    return str(job.id)
