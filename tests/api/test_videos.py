"""`POST /api/v1/videos` のテスト.

unit: 拡張子バリデーション 400 (DB / Ingest に到達しない).
integration: 実 Postgres + 実 ObjectStore で 201 まで到達する正常系.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlmodel import col

from clipmind.api.deps import get_object_store, get_settings
from clipmind.api.main import create_app
from clipmind.config import Settings
from clipmind.storage.db import get_session_maker
from clipmind.storage.models import Video
from clipmind.storage.object_store import LocalFSObjectStore


@pytest.mark.asyncio
async def test_upload_video_rejects_bad_extension(tmp_path: Path) -> None:
    """サポート外拡張子は 400 (DB / Ingest に到達しない)."""
    get_settings.cache_clear()
    get_object_store.cache_clear()

    settings = Settings(data_dir=tmp_path)

    def _store() -> LocalFSObjectStore:
        return LocalFSObjectStore(base_dir=settings.object_store_dir)

    app = create_app()
    app.dependency_overrides[get_object_store] = _store

    files = {"file": ("doc.pdf", b"not a video", "application/pdf")}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v1/videos", files=files)
    assert resp.status_code == 400


@pytest.mark.integration
async def test_upload_video_accepts_mp4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mp4 アップロード → 201 (実 Postgres、Ingest は OpenCV/ffmpeg なしの合成).

    Ingest 内部の `run_ingest` は noop に差し替え (audio/whisper を呼ばないため).
    """
    get_settings.cache_clear()
    get_object_store.cache_clear()

    settings = Settings(data_dir=tmp_path)

    def _settings() -> Settings:
        return settings

    def _store() -> LocalFSObjectStore:
        return LocalFSObjectStore(base_dir=settings.object_store_dir)

    async def _noop_run_ingest(*_a: object, **_kw: object) -> dict[str, object]:
        return {}

    monkeypatch.setattr("clipmind.api.routes.videos.run_ingest", _noop_run_ingest)

    app = create_app()
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_object_store] = _store

    # SHA256 重複を避けるため毎テストで unique payload
    payload = b"\x00\x00\x00\x18ftypisom" + secrets.token_bytes(256)
    files = {"file": ("sample.mp4", payload, "video/mp4")}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v1/videos", files=files)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["sha256"]
    assert body["object_store_key"].endswith(".mp4")

    # GET /api/v1/videos/{id} で 200 が返る
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        detail = await client.get(f"/api/v1/videos/{body['video_id']}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["sha256"] == body["sha256"]

    # cleanup
    from uuid import UUID

    maker = get_session_maker()
    async with maker() as session:
        await session.execute(delete(Video).where(col(Video.id) == UUID(body["video_id"])))
        await session.commit()
