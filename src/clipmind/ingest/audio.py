"""ffmpeg を呼び出して動画から 16kHz mono wav を抽出する.

ffmpeg はシステム依存. 未インストールなら RuntimeError.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


class FfmpegNotFoundError(RuntimeError):
    """ffmpeg バイナリがシステムに見つからない."""


def _resolve_ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        msg = "ffmpeg not found on PATH. Install via `brew install ffmpeg`."
        raise FfmpegNotFoundError(msg)
    return binary


async def extract_audio(video_path: Path, output_path: Path) -> Path:
    """`video_path` から音声を抽出して `output_path` に 16kHz mono wav を書き出す.

    Returns:
        output_path
    """
    ffmpeg = _resolve_ffmpeg()
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
