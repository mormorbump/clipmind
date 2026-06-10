"""faster-whisper の実 transcribe テスト (e2e).

macOS `say` で合成した実音声から「何らかの英語テキスト」が返ることを確認する.
モデルダウンロード (~150MB) が走るため CI ではスキップ、ローカルで明示実行:

    uv run pytest -m e2e tests/ingest/test_transcriber.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clipmind.ingest.audio import extract_audio
from clipmind.ingest.transcriber import transcribe

pytestmark = pytest.mark.e2e


async def test_transcribe_returns_text_from_spoken_video(
    spoken_video: Path, tmp_path: Path
) -> None:
    """実音声つき動画 → wav → transcript に 'quarter' 系の単語が含まれる."""
    wav = await extract_audio(spoken_video, tmp_path / "speech.wav")
    segments = transcribe(wav, model_size="base", language="en")

    assert len(segments) >= 1
    full_text = " ".join(s.text for s in segments).lower()
    # 厳密一致は脆いので、特徴的な単語のどれかが拾えていれば OK
    assert any(word in full_text for word in ("quarter", "revenue", "review", "results")), (
        f"unexpected transcript: {full_text!r}"
    )
    # タイムスタンプが単調増加
    starts = [s.start for s in segments]
    assert starts == sorted(starts)
