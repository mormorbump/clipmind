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
