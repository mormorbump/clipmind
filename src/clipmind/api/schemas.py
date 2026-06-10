"""Pydantic v2 Request / Response スキーマ."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DepsStatus(BaseModel):
    """`/health` の `deps` 中身."""

    model_config = ConfigDict(extra="forbid")

    postgres: Literal["ok", "error", "skipped"] = "skipped"
    redis: Literal["ok", "error", "skipped"] = "skipped"
    qdrant: Literal["ok", "error", "skipped"] = "skipped"
    anthropic: Literal["ok", "error", "skipped"] = "skipped"


class HealthResponse(BaseModel):
    """`GET /health` のレスポンス."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "degraded"] = "healthy"
    deps: DepsStatus = Field(default_factory=DepsStatus)


class VideoCreatedResponse(BaseModel):
    """`POST /api/v1/videos` のレスポンス."""

    model_config = ConfigDict(extra="forbid")

    video_id: str
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    sha256: str
    object_store_key: str
    object_store_url: str


class VideoDetailResponse(BaseModel):
    """`GET /api/v1/videos/{video_id}` のレスポンス."""

    model_config = ConfigDict(extra="forbid")

    video_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    sha256: str
    duration_seconds: float | None = None
    frame_count: int = 0
    transcript_segment_count: int = 0
    created_at: datetime
    completed_at: datetime | None = None
