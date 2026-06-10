"""LangGraph IngestState 定義.

architecture.md §3.1 に従い、並列ノードの結果を Reducer で安全にマージする形で定義.
Phase 1 では並列ノードは無いが、Phase 2 で YOLO / Caption 並列化に備えて前方互換にしておく.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict


class Frame(TypedDict):
    """キーフレーム 1 枚を表す軽量レコード."""

    index: int
    timestamp_ms: int
    object_store_key: str


class TranscriptSegment(TypedDict):
    """Whisper が返す 1 セグメント."""

    start_ms: int
    end_ms: int
    text: str


class DetectionRecord(TypedDict):
    """YOLO 検知結果 1 件."""

    frame_index: int
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]


class Caption(TypedDict):
    """フレームキャプション 1 件."""

    frame_index: int
    text: str
    model: str


class IngestState(TypedDict, total=False):
    """LangGraph で流れる State.

    並列ノードを後で追加するため `Annotated[list, add]` で Reducer 付き定義としている.
    YAGNI 違反すれすれだが ADR-0001 に沿った前方互換のための判断（phase-1-plan.md 参照）.
    """

    video_id: str
    source: Literal["local", "url"]
    video_path: str
    audio_path: str | None

    frames: Annotated[list[Frame], add]
    transcripts: Annotated[list[TranscriptSegment], add]
    detections: Annotated[list[DetectionRecord], add]
    captions: Annotated[list[Caption], add]
    errors: Annotated[list[str], add]
