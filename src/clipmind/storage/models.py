"""SQLModel テーブル定義.

Phase 1: Video / Frame / TranscriptSegment の 3 テーブル.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index
from sqlmodel import Field, SQLModel


class Video(SQLModel, table=True):
    """ユーザーがアップロードした動画."""

    __tablename__ = "videos"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sha256: str = Field(index=True, unique=True, max_length=64)
    source_type: str = Field(default="local", max_length=16)
    object_store_key: str = Field(max_length=512)
    duration_seconds: float | None = Field(default=None)
    status: str = Field(default="queued", max_length=16, index=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class Frame(SQLModel, table=True):
    """OpenCV で抽出したキーフレーム."""

    __tablename__ = "frames"
    __table_args__ = (Index("ix_frames_video_ts", "video_id", "timestamp_ms"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    video_id: UUID = Field(
        sa_column=Column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    frame_index: int
    timestamp_ms: int
    object_store_key: str = Field(max_length=512)


class TranscriptSegment(SQLModel, table=True):
    """faster-whisper の transcript 1 セグメント."""

    __tablename__ = "transcript_segments"
    __table_args__ = (Index("ix_segments_video_start", "video_id", "start_ms"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    video_id: UUID = Field(
        sa_column=Column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    start_ms: int
    end_ms: int
    text: str


class Detection(SQLModel, table=True):
    """YOLO 物体検知 1 件 (Phase 2)."""

    __tablename__ = "detections"
    __table_args__ = (Index("ix_detections_video_frame", "video_id", "frame_index"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    video_id: UUID = Field(
        sa_column=Column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    frame_index: int
    label: str = Field(max_length=64, index=True)
    confidence: float
    bbox_x1: int
    bbox_y1: int
    bbox_x2: int
    bbox_y2: int


class FrameCaption(SQLModel, table=True):
    """マルチモーダル LLM のフレームキャプション 1 件 (Phase 2)."""

    __tablename__ = "frame_captions"
    __table_args__ = (Index("ix_captions_video_frame", "video_id", "frame_index"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    video_id: UUID = Field(
        sa_column=Column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    frame_index: int
    text: str
    model: str = Field(max_length=64)
