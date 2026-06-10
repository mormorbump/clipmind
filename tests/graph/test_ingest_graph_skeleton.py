"""LangGraph 雛形が compile して run できることだけ確認."""

from __future__ import annotations

from pathlib import Path

import pytest

from clipmind.graph.ingest_graph import build_ingest_graph_skeleton


@pytest.mark.asyncio
async def test_ingest_graph_compiles_and_runs(tmp_path: Path) -> None:
    """validate ノードだけ通る最小グラフが compile & invoke できること."""
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"\x00" * 16)

    graph = build_ingest_graph_skeleton().compile()
    result = await graph.ainvoke(
        {"video_id": "vid_test", "source": "local", "video_path": str(sample)}
    )

    assert result["video_id"] == "vid_test"
    assert result.get("errors", []) == []


@pytest.mark.asyncio
async def test_ingest_graph_records_missing_file_error() -> None:
    """存在しないファイルだと errors に追記される."""
    graph = build_ingest_graph_skeleton().compile()
    result = await graph.ainvoke(
        {"video_id": "vid_x", "source": "local", "video_path": "/nope/does-not-exist.mp4"}
    )
    assert any("video_path not found" in e for e in result["errors"])
