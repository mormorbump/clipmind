"""時刻窓で transcript / detection / caption を束ねて検索単位 (segment) を作る.

architecture.md §3.3 の fuse 戦略. この segment が RAG の chunk になる.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from clipmind.storage.models import Detection, FrameCaption, TranscriptSegment


@dataclass
class TimelineSegment:
    """検索単位 1 つ (時刻窓)."""

    video_id: UUID
    start_ms: int
    end_ms: int
    transcript: str = ""
    objects: list[str] = field(default_factory=list)
    captions: list[str] = field(default_factory=list)

    @property
    def search_text(self) -> str:
        """embedding / BM25 にかける統合テキスト."""
        parts = []
        if self.transcript:
            parts.append(self.transcript)
        if self.captions:
            parts.append(" ".join(self.captions))
        if self.objects:
            parts.append("objects: " + ", ".join(sorted(set(self.objects))))
        return "\n".join(parts)


def fuse_timeline(
    video_id: UUID,
    transcripts: list[TranscriptSegment],
    detections: list[Detection],
    captions: list[FrameCaption],
    frame_timestamps: dict[int, int],
    *,
    window_ms: int = 5000,
    duration_ms: int | None = None,
) -> list[TimelineSegment]:
    """5 秒窓 (デフォルト) で各情報を束ねる.

    Args:
        frame_timestamps: frame_index → timestamp_ms (detection/caption の時刻解決に使う)
        duration_ms: None なら全データの最大時刻から推定
    """
    if duration_ms is None:
        candidates = [t.end_ms for t in transcripts]
        candidates += [frame_timestamps.get(d.frame_index, 0) for d in detections]
        candidates += [frame_timestamps.get(c.frame_index, 0) for c in captions]
        duration_ms = max(candidates, default=0)

    if duration_ms <= 0:
        return []

    segments: list[TimelineSegment] = []
    for start in range(0, duration_ms + 1, window_ms):
        end = start + window_ms
        seg = TimelineSegment(video_id=video_id, start_ms=start, end_ms=end)

        seg.transcript = " ".join(
            t.text for t in transcripts if t.start_ms < end and t.end_ms > start
        )
        seg.objects = [
            d.label for d in detections if start <= frame_timestamps.get(d.frame_index, -1) < end
        ]
        seg.captions = [
            c.text for c in captions if start <= frame_timestamps.get(c.frame_index, -1) < end
        ]

        if seg.search_text:
            segments.append(seg)
    return segments
