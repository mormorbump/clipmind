"""ffmpeg を呼び出して動画から 16kHz mono wav を抽出する.

ffmpeg はシステム依存. 未インストールなら RuntimeError.
音声ストリームが無い動画 (cv2.VideoWriter 出力等) は NoAudioStreamError.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


class FfmpegNotFoundError(RuntimeError):
    """ffmpeg / ffprobe バイナリがシステムに見つからない."""


class NoAudioStreamError(RuntimeError):
    """動画に音声ストリームが含まれていない."""


def _resolve_binary(name: str) -> str:
    binary = shutil.which(name)
    if binary is None:
        msg = f"{name} not found on PATH. Install via `brew install ffmpeg`."
        raise FfmpegNotFoundError(msg)
    return binary


async def has_audio_stream(video_path: Path) -> bool:
    """ffprobe で音声ストリームの有無を判定する."""
    ffprobe = _resolve_binary("ffprobe")
    args = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return bool(stdout.strip())


async def extract_audio(video_path: Path, output_path: Path) -> Path:
    """`video_path` から音声を抽出して `output_path` に 16kHz mono wav を書き出す.

    Raises:
        FfmpegNotFoundError: ffmpeg が PATH に無い
        NoAudioStreamError: 動画に音声ストリームが無い
        RuntimeError: ffmpeg がその他の理由で失敗
    """
    ffmpeg = _resolve_binary("ffmpeg")

    if not await has_audio_stream(video_path):
        msg = f"no audio stream in {video_path}"
        raise NoAudioStreamError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    args = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(output_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = f"ffmpeg failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
        raise RuntimeError(msg)
    return output_path
