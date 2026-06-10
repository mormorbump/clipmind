"""fuse_timeline の unit テスト (DB / Qdrant 不要)."""

from __future__ import annotations

from uuid import uuid4

from clipmind.rag.fuse import fuse_timeline
from clipmind.storage.models import Detection, FrameCaption, TranscriptSegment


def test_fuse_groups_by_window() -> None:
    """transcript / detection / caption が 5 秒窓に正しく振り分けられる."""
    vid = uuid4()
    transcripts = [
        TranscriptSegment(video_id=vid, start_ms=0, end_ms=3000, text="hello world"),
        TranscriptSegment(video_id=vid, start_ms=6000, end_ms=9000, text="second window"),
    ]
    detections = [
        Detection(
            video_id=vid,
            frame_index=0,
            label="person",
            confidence=0.9,
            bbox_x1=0,
            bbox_y1=0,
            bbox_x2=10,
            bbox_y2=10,
        ),
    ]
    captions = [
        FrameCaption(video_id=vid, frame_index=5, text="a person talking", model="m"),
    ]
    # frame 0 → 1000ms (窓 1), frame 5 → 7000ms (窓 2)
    frame_ts = {0: 1000, 5: 7000}

    segments = fuse_timeline(vid, transcripts, detections, captions, frame_ts)

    assert len(segments) == 2
    first, second = segments
    assert first.start_ms == 0
    assert "hello world" in first.search_text
    assert "person" in first.search_text  # detection label
    assert second.start_ms == 5000
    assert "second window" in second.search_text
    assert "a person talking" in second.search_text


def test_fuse_transcript_spanning_windows_appears_in_both() -> None:
    """窓境界をまたぐ transcript は両方の窓に含まれる."""
    vid = uuid4()
    transcripts = [
        TranscriptSegment(video_id=vid, start_ms=4000, end_ms=6000, text="spanning"),
    ]
    segments = fuse_timeline(vid, transcripts, [], [], {}, duration_ms=10000)
    spanning = [s for s in segments if "spanning" in s.search_text]
    assert {s.start_ms for s in spanning} == {0, 5000}


def test_fuse_empty_input_returns_empty() -> None:
    assert fuse_timeline(uuid4(), [], [], [], {}) == []
