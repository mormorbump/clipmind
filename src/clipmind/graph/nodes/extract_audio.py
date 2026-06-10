"""extract_audio ノード: video_path → audio_path (16kHz mono wav).

音声ストリームが無い動画は audio_path=None のまま下流に流す (エラー扱いしない).
ffmpeg 不在やその他の失敗は errors に追記する.
"""

from __future__ import annotations

from pathlib import Path

from clipmind.graph.state import IngestState
from clipmind.ingest.audio import FfmpegNotFoundError, NoAudioStreamError, extract_audio


def make_extract_audio_node(audio_dir: Path):  # type: ignore[no-untyped-def]
    """`audio_dir/<video_id>.wav` に書き出すノードを返す."""

    async def extract_audio_node(state: IngestState) -> IngestState:
        video_path = state.get("video_path")
        if not video_path:
            return {"errors": ["extract_audio: video_path is empty"]}

        video_id = state.get("video_id", "unknown")
        out_path = audio_dir / f"{video_id}.wav"
        try:
            await extract_audio(Path(video_path), out_path)
        except NoAudioStreamError:
            # 無音動画は正常系: transcript なしで進む
            return {"audio_path": None}
        except FfmpegNotFoundError as e:
            return {"errors": [f"extract_audio: {e}"]}
        except RuntimeError as e:
            return {"errors": [f"extract_audio: {e}"]}
        return {"audio_path": str(out_path)}

    return extract_audio_node
