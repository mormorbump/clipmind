"""ffmpeg 音声抽出のテスト.

ffmpeg バイナリが無い環境では unit パスで RuntimeError を返すことだけ確認.
ffmpeg が有る環境では integration で実体抽出まで確認.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from clipmind.ingest.audio import FfmpegNotFoundError, extract_audio


async def test_extract_audio_raises_without_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`shutil.which` が None を返す状況で FfmpegNotFoundError."""
    monkeypatch.setattr("clipmind.ingest.audio.shutil.which", lambda _name: None)
    with pytest.raises(FfmpegNotFoundError):
        await extract_audio(tmp_path / "in.mp4", tmp_path / "out.wav")


@pytest.mark.integration
async def test_extract_audio_writes_wav(synthetic_video: Path, tmp_path: Path) -> None:
    """ffmpeg があれば 16kHz mono wav が書き出される."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    out = await extract_audio(synthetic_video, tmp_path / "audio.wav")
    assert out.is_file()
    assert out.stat().st_size > 0
    # RIFF/WAVE ヘッダ確認
    head = out.read_bytes()[:12]
    assert head[:4] == b"RIFF"
    assert head[8:12] == b"WAVE"
