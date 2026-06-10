"""faster-whisper を使った transcript 生成.

ADR / knowledge/whisper-stt/01 に従い:
- macOS Apple Silicon 想定 → CPU + int8 量子化で確実動作
- VAD filter ON で無音区間スキップ
- モデルは Phase 1 では "base" 固定 (large は将来)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faster_whisper import WhisperModel


@dataclass(frozen=True)
class TranscriptionSegment:
    """Whisper の 1 セグメント (start/end は秒)."""

    start: float
    end: float
    text: str
    no_speech_prob: float


def _load_model(model_size: str = "base") -> WhisperModel:
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe(
    audio_path: Path,
    *,
    model_size: str = "base",
    language: str | None = None,
    vad_filter: bool = True,
    no_speech_threshold: float = 0.6,
) -> list[TranscriptionSegment]:
    """`audio_path` を transcribe して segment 列を返す.

    Args:
        audio_path: 16kHz mono wav 推奨
        model_size: tiny / base / small / medium / large-v3
        language: None なら自動検出, "ja" / "en" 等で固定可
        vad_filter: VAD で無音区間をスキップ
        no_speech_threshold: no_speech_prob > これ の segment は捨てる
    """
    model = _load_model(model_size)
    raw_segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=vad_filter,
        beam_size=1,
    )
    out: list[TranscriptionSegment] = []
    for seg in raw_segments:
        if seg.no_speech_prob is not None and seg.no_speech_prob > no_speech_threshold:
            continue
        text = seg.text.strip()
        if not text:
            continue
        out.append(
            TranscriptionSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=text,
                no_speech_prob=float(seg.no_speech_prob or 0.0),
            )
        )
    return out
