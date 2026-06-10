"""ffmpeg 音声抽出のテスト.

- unit: ffmpeg 不在で FfmpegNotFoundError
- integration: 音声つき動画から 16kHz mono wav / 無音動画で NoAudioStreamError
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from clipmind.ingest.audio import (
    FfmpegNotFoundError,
    NoAudioStreamError,
    extract_audio,
    has_audio_stream,
)


async def test_extract_audio_raises_without_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`shutil.which` が None を返す状況で FfmpegNotFoundError."""
    monkeypatch.setattr("clipmind.ingest.audio.shutil.which", lambda _name: None)
    with pytest.raises(FfmpegNotFoundError):
        await extract_audio(tmp_path / "in.mp4", tmp_path / "out.wav")


@pytest.mark.integration
async def test_extract_audio_writes_wav(synthetic_video_with_audio: Path, tmp_path: Path) -> None:
    """音声つき動画なら 16kHz mono wav が書き出される."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    out = await extract_audio(synthetic_video_with_audio, tmp_path / "audio.wav")
    assert out.is_file()
    assert out.stat().st_size > 0
    head = out.read_bytes()[:12]
    assert head[:4] == b"RIFF"
    assert head[8:12] == b"WAVE"


@pytest.mark.integration
async def test_extract_audio_raises_on_silent_video(synthetic_video: Path, tmp_path: Path) -> None:
    """cv2.VideoWriter 出力 (音声なし) は NoAudioStreamError."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    assert not await has_audio_stream(synthetic_video)
    with pytest.raises(NoAudioStreamError):
        await extract_audio(synthetic_video, tmp_path / "audio.wav")
