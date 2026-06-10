"""共通 fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture(autouse=True)
async def _reset_db_engine_per_test() -> AsyncIterator[None]:
    """各テスト終了時に engine をリセット.

    pytest-asyncio 1.x は各テストで独自 event loop を作る. asyncpg connection は
    作成時の loop に紐づくため、テスト跨ぎで engine を持ち回すと次テストで
    `Event loop is closed` で爆発する. 毎回 dispose して新規に作り直す.
    """
    yield
    try:
        from clipmind.storage.db import dispose_engine

        await dispose_engine()
    except Exception:
        pass


@pytest.fixture
def synthetic_video(tmp_path: Path) -> Iterator[Path]:
    """色が途中で変わる 5 秒動画を OpenCV だけで生成して返す (ffmpeg 不要).

    内訳 (5 fps × 5 秒 = 25 フレーム):
      - 0..12 : 赤一色
      - 13..24: 青一色
    シーンカット検出の正常系を確認するのに使う.
    """
    out_path = tmp_path / "synthetic_5s.mp4"
    width, height, fps = 64, 64, 5
    # mp4v は OpenCV ビルドに広く含まれる. 失敗したら他コーデックにフォールバック.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        pytest.skip("cv2.VideoWriter could not open with mp4v")

    red = np.zeros((height, width, 3), dtype=np.uint8)
    red[:, :, 2] = 200  # B,G,R
    blue = np.zeros((height, width, 3), dtype=np.uint8)
    blue[:, :, 0] = 200

    for i in range(25):
        writer.write(red if i < 13 else blue)
    writer.release()

    assert out_path.exists() and out_path.stat().st_size > 0
    yield out_path
