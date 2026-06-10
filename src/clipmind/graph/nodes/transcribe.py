"""transcribe ノード: audio_path → TranscriptSegment[].

faster-whisper は同期 + GIL を解放する CPU bound. asyncio.to_thread で実行.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from clipmind.graph.state import IngestState, TranscriptSegment
from clipmind.ingest.transcriber import transcribe


def make_transcribe_node(model_size: str = "base"):  # type: ignore[no-untyped-def]
    """`model_size` を閉じ込んだノード関数を返す."""

    async def transcribe_node(state: IngestState) -> IngestState:
        audio_path = state.get("audio_path")
        if not audio_path:
            return {"errors": ["transcribe: audio_path is empty"]}

        try:
            segments = await asyncio.to_thread(transcribe, Path(audio_path), model_size=model_size)
        except Exception as e:
            return {"errors": [f"transcribe: {e}"]}

        transcripts: list[TranscriptSegment] = [
            TranscriptSegment(
                start_ms=int(seg.start * 1000),
                end_ms=int(seg.end * 1000),
                text=seg.text,
            )
            for seg in segments
        ]
        return {"transcripts": transcripts}

    return transcribe_node
