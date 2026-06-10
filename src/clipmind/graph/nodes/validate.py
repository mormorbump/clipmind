"""validate ノード: video_path の存在確認のみ.

Phase 1 のシンプル実装. 実体ファイルが存在しなければ errors に追記して下流に流す.
"""

from __future__ import annotations

from pathlib import Path

from clipmind.graph.state import IngestState


def validate_input(state: IngestState) -> IngestState:
    """video_path の妥当性検証."""
    video_path = state.get("video_path")
    if not video_path or not Path(video_path).is_file():
        return {"errors": [f"video_path not found: {video_path!r}"]}
    return {}
