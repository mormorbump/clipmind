"""`POST /api/v1/videos` / `GET /api/v1/videos/{video_id}` エンドポイント.

M1-5: アップロード → ObjectStore 保存 → DB に Video 作成 → LangGraph Ingest 起動.
Phase 1 は同期実行 (Plan 通り). Phase 8 で WebSocket 進捗 + RQ に切替予定.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clipmind.api.deps import get_object_store, get_settings
from clipmind.api.schemas import VideoCreatedResponse, VideoDetailResponse
from clipmind.config import Settings
from clipmind.graph.runner import run_ingest
from clipmind.storage.db import get_session_maker
from clipmind.storage.object_store import ObjectStore
from clipmind.storage.repositories.video import VideoRepository

router = APIRouter(prefix="/api/v1/videos", tags=["videos"])

ALLOWED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2GB
CHUNK_SIZE = 64 * 1024  # 64KiB


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    """DI 用ラッパ (tests で override 可能に)."""
    return get_session_maker()


@router.post(
    "",
    response_model=VideoCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_video(
    file: UploadFile,
    object_store: Annotated[ObjectStore, Depends(get_object_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_maker: Annotated[async_sessionmaker[AsyncSession], Depends(_get_session_maker)],
) -> VideoCreatedResponse:
    """multipart アップロードを受け取り Ingest を起動する.

    Phase 1 は同期実行のためレスポンスを返すまでに Whisper の処理時間がかかる.
    """
    filename = file.filename or "video.bin"
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported file extension: {suffix!r}",
        )

    hasher = hashlib.sha256()
    buf = bytearray()
    total = 0
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="upload exceeds 2GB",
            )
        hasher.update(chunk)
        buf.extend(chunk)

    sha256 = hasher.hexdigest()

    # 重複アップロード検出 (sha256 一致なら 409)
    async with session_maker() as session:
        repo = VideoRepository(session)
        existing = await repo.get_by_sha256(sha256)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"video_id": str(existing.id), "sha256": sha256},
            )

        video_uuid = uuid4()
        key = f"videos/{video_uuid.hex}/original{suffix}"
        await object_store.put(key, bytes(buf))
        await repo.create(
            sha256=sha256,
            object_store_key=key,
        )
        # create() が default UUID で発番するため、戻り値の id を使うために再 select
        created = await repo.get_by_sha256(sha256)
        if created is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="video disappeared after create",
            )
        video_uuid = created.id

    if settings.enable_async_ingest:
        # Phase 8: RQ ワーカーに退避 (202 Accepted 相当. 進捗は WS で配信)
        from clipmind.worker import enqueue_ingest

        enqueue_ingest(settings.redis_url, video_uuid.hex, key)
    else:
        # 同期実行. 失敗しても 201 は返し、DB の status で表現.
        try:
            from clipmind.api.deps import get_segment_index
            from clipmind.llm.factory import build_captioner

            await run_ingest(
                video_id=video_uuid.hex,
                video_path=Path(settings.object_store_dir / key),
                object_store=object_store,
                audio_dir=settings.data_dir / "audio",
                checkpoint_db_path=settings.checkpoint_db_path,
                session_maker=session_maker,
                captioner=build_captioner(settings),
                segment_index=get_segment_index() if settings.enable_indexing else None,
                whisper_model_size=settings.whisper_model_size,
                enable_detection=settings.enable_detection,
                max_caption_frames=settings.max_caption_frames,
            )
        except Exception:
            async with session_maker() as session:
                repo = VideoRepository(session)
                video = await repo.get(video_uuid)
                if video is not None:
                    video.status = "failed"
                    await session.commit()

    return VideoCreatedResponse(
        video_id=str(video_uuid),
        status="queued",
        sha256=sha256,
        object_store_key=key,
        object_store_url=object_store.url_for(key),
    )


@router.get("/{video_id}", response_model=VideoDetailResponse)
async def get_video(
    video_id: str,
    session_maker: Annotated[async_sessionmaker[AsyncSession], Depends(_get_session_maker)],
) -> VideoDetailResponse:
    """Video のメタデータ + frame/transcript 件数を返す."""
    from uuid import UUID

    try:
        video_uuid = UUID(video_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid video_id") from e

    async with session_maker() as session:
        repo = VideoRepository(session)
        video = await repo.get(video_uuid)
        if video is None:
            raise HTTPException(status_code=404, detail="video not found")
        frame_count = await repo.count_frames(video_uuid)
        seg_count = await repo.count_transcript_segments(video_uuid)

    return VideoDetailResponse.model_validate(
        {
            "video_id": str(video.id),
            "status": video.status,
            "sha256": video.sha256,
            "duration_seconds": video.duration_seconds,
            "frame_count": frame_count,
            "transcript_segment_count": seg_count,
            "created_at": video.created_at,
            "completed_at": video.completed_at,
        }
    )


class VideoListItem(VideoDetailResponse):
    """一覧用 (詳細と同形)."""


@router.get("", response_model=list[VideoListItem])
async def list_videos(
    session_maker: Annotated[async_sessionmaker[AsyncSession], Depends(_get_session_maker)],
    limit: int = 50,
) -> list[VideoListItem]:
    """直近の動画一覧 (UI の動画セレクタ用)."""
    async with session_maker() as session:
        repo = VideoRepository(session)
        videos = await repo.list_recent(limit=min(limit, 200))
        items: list[VideoListItem] = []
        for v in videos:
            frame_count = await repo.count_frames(v.id)
            seg_count = await repo.count_transcript_segments(v.id)
            items.append(
                VideoListItem.model_validate(
                    {
                        "video_id": str(v.id),
                        "status": v.status,
                        "sha256": v.sha256,
                        "duration_seconds": v.duration_seconds,
                        "frame_count": frame_count,
                        "transcript_segment_count": seg_count,
                        "created_at": v.created_at,
                        "completed_at": v.completed_at,
                    }
                )
            )
    return items


@router.get("/{video_id}/progress")
async def get_progress(
    video_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Ingest 進捗の最新イベント (Redis 保存値) を返す. UI のポーリング用.

    WS (/ws/videos/{id}/progress) のフォールバック. Redis 不通や記録なしは
    stage="unknown" を返す.
    """
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
        try:
            raw = await client.get(f"clipmind:progress-latest:{video_id.replace('-', '')}")
            if raw is None:
                raw = await client.get(f"clipmind:progress-latest:{video_id}")
        finally:
            await client.aclose()
    except Exception:
        return {"stage": "unknown", "progress": 0.0}

    if raw is None:
        return {"stage": "unknown", "progress": 0.0}
    import json

    return dict(json.loads(raw))


@router.get("/{video_id}/frame")
async def get_nearest_frame(
    video_id: str,
    session_maker: Annotated[async_sessionmaker[AsyncSession], Depends(_get_session_maker)],
    object_store: Annotated[ObjectStore, Depends(get_object_store)],
    timestamp_ms: int = 0,
) -> dict[str, object]:
    """指定時刻に最も近いキーフレームの URL を返す (検索結果のサムネイル用)."""
    from uuid import UUID

    try:
        video_uuid = UUID(video_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid video_id") from e

    async with session_maker() as session:
        repo = VideoRepository(session)
        frame = await repo.nearest_frame(video_uuid, timestamp_ms)
    if frame is None:
        raise HTTPException(status_code=404, detail="no frames for video")
    return {
        "frame_url": object_store.url_for(frame.object_store_key),
        "timestamp_ms": frame.timestamp_ms,
        "frame_index": frame.frame_index,
    }
