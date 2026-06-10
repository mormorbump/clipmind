"""extract_keyframes の最小テスト.

赤→青 と途中で切り替わる合成動画なら、最低 2 枚のキーフレームが採用されるべき.
"""

from __future__ import annotations

from pathlib import Path

from clipmind.ingest.frames import extract_keyframes


def test_extract_keyframes_detects_scene_change(synthetic_video: Path) -> None:
    """合成動画 (赤→青) に対してキーフレームが 2 枚以上採用される."""
    frames = extract_keyframes(synthetic_video, threshold=0.3, min_gap_frames=3)

    assert len(frames) >= 2, f"expected >=2 keyframes, got {len(frames)}"
    assert frames[0].index == 0
    assert all(f.jpeg_bytes.startswith(b"\xff\xd8") for f in frames)  # JPEG SOI
    timestamps = [f.timestamp_ms for f in frames]
    assert timestamps == sorted(timestamps)
