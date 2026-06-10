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
def synthetic_video_with_audio(tmp_path: Path) -> Iterator[Path]:
    """ffmpeg の lavfi で「赤→青 + 440Hz サイン波音声」の 5 秒 mp4 を生成する.

    ffmpeg 必須なので integration テスト用.
    """
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")

    out_path = tmp_path / "synthetic_with_audio_5s.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:size=64x64:duration=2.5:rate=5",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:size=64x64:duration=2.5:rate=5",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=5",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "2:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert out_path.exists() and out_path.stat().st_size > 0
    yield out_path


@pytest.fixture
def spoken_video(tmp_path: Path) -> Iterator[Path]:
    """macOS `say` で実音声 (英語) を合成し、動画に mux した 30 秒弱の mp4.

    Whisper の transcript 確認 (e2e) 用. macOS + ffmpeg 必須.
    """
    import platform
    import shutil
    import subprocess

    if platform.system() != "Darwin":
        pytest.skip("spoken_video fixture requires macOS `say`")
    if shutil.which("ffmpeg") is None or shutil.which("say") is None:
        pytest.skip("ffmpeg / say not installed")

    aiff = tmp_path / "speech.aiff"
    text = (
        "Welcome to the quarterly review. "
        "Today we will discuss the third quarter results. "
        "Revenue increased by twenty percent compared to last year. "
        "The new product line exceeded all expectations. "
        "Thank you for joining this presentation."
    )
    subprocess.run(["say", "-o", str(aiff), text], check=True, capture_output=True)

    out_path = tmp_path / "spoken_video.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(aiff),
        "-f",
        "lavfi",
        "-i",
        "color=c=darkgreen:size=64x64:rate=5",
        "-shortest",
        "-map",
        "1:v",
        "-map",
        "0:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert out_path.exists() and out_path.stat().st_size > 0
    yield out_path


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
