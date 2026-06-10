"""UI 用補助エンドポイントのテスト (一覧 / 進捗 / 最寄りフレーム)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlmodel import col

from clipmind.api.main import create_app

pytestmark = pytest.mark.integration


async def test_list_videos_and_nearest_frame(tmp_path: object) -> None:
    """一覧に登録済み動画が出て、frame エンドポイントが最寄りを返す."""
    from clipmind.storage.db import get_session_maker
    from clipmind.storage.models import Frame, Video

    maker = get_session_maker()
    vid = uuid4()
    async with maker() as session:
        session.add(Video(id=vid, sha256=vid.hex, object_store_key="videos/x/original.mp4"))
        await session.flush()
        session.add(Frame(video_id=vid, frame_index=0, timestamp_ms=0, object_store_key="f/a.jpg"))
        session.add(
            Frame(video_id=vid, frame_index=5, timestamp_ms=5000, object_store_key="f/b.jpg")
        )
        await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            # 一覧
            resp = await http.get("/api/v1/videos")
            assert resp.status_code == 200
            ids = [v["video_id"] for v in resp.json()]
            assert str(vid) in ids

            # 最寄りフレーム: 4000ms に近いのは 5000ms 側
            resp = await http.get(f"/api/v1/videos/{vid}/frame", params={"timestamp_ms": 4000})
            assert resp.status_code == 200
            body = resp.json()
            assert body["timestamp_ms"] == 5000
            assert body["frame_url"].endswith("f/b.jpg")

            # 進捗: 記録なしの動画は unknown
            resp = await http.get(f"/api/v1/videos/{vid}/progress")
            assert resp.status_code == 200
            assert resp.json()["stage"] in ("unknown", "completed")
    finally:
        async with maker() as session:
            await session.execute(delete(Video).where(col(Video.id) == vid))
            await session.commit()
