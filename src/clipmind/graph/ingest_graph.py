"""Ingest StateGraph 構築.

Phase 2 で fan-out / fan-in 構造に拡張 (architecture.md §3.2):

    validate → extract_frames ─┬→ extract_audio → transcribe ─┐
                               ├→ detect_objects ─────────────┼→ store
                               └→ caption_frames ─────────────┘

並列 3 経路が同じ State の `errors` 等に書き込むため、
`Annotated[list, add]` の Reducer (state.py) がここで初めて本領を発揮する.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from clipmind.graph.nodes.caption_frames import make_caption_frames_node
from clipmind.graph.nodes.detect_objects import make_detect_objects_node
from clipmind.graph.nodes.extract_audio import make_extract_audio_node
from clipmind.graph.nodes.extract_frames import make_extract_frames_node
from clipmind.graph.nodes.index_segments import make_index_segments_node
from clipmind.graph.nodes.store import make_store_node
from clipmind.graph.nodes.transcribe import make_transcribe_node
from clipmind.graph.nodes.validate import validate_input
from clipmind.graph.state import IngestState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from clipmind.llm.captioner import Captioner
    from clipmind.rag.indexer import SegmentIndex
    from clipmind.storage.object_store import ObjectStore


def build_ingest_graph_skeleton() -> StateGraph[IngestState, None, IngestState, IngestState]:
    """M1-1 互換: ノード validate のみの最小グラフ.

    `build_ingest_graph` を使えない場面 (DB 不要な smoke test 等) の保険.
    """
    graph: StateGraph[IngestState, None, IngestState, IngestState] = StateGraph(IngestState)
    graph.add_node("validate", validate_input)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", END)
    return graph


def build_ingest_graph(
    *,
    object_store: ObjectStore,
    audio_dir: Path,
    session_maker: async_sessionmaker[AsyncSession],
    captioner: Captioner,
    segment_index: SegmentIndex | None = None,
    whisper_model_size: str = "base",
    enable_detection: bool = True,
    max_caption_frames: int | None = 20,
) -> StateGraph[IngestState, None, IngestState, IngestState]:
    """fan-out 付き Ingest グラフを返す (compile 前).

    `store` の `# type: ignore[arg-type]` は LangGraph 1.2 の `add_node` が
    `_Node[Never]` を期待する型ナローイング問題への対処. ランタイム挙動には影響しない.

    Args:
        segment_index: None なら Qdrant インデックス (index ノード) を外す
        enable_detection: False なら YOLO 経路を外す (テスト高速化用)
        max_caption_frames: キャプション対象フレーム数の上限 (コスト制御)
    """
    graph: StateGraph[IngestState, None, IngestState, IngestState] = StateGraph(IngestState)
    graph.add_node("validate", validate_input)
    graph.add_node("extract_frames", make_extract_frames_node(object_store))
    graph.add_node("extract_audio", make_extract_audio_node(audio_dir))
    graph.add_node("transcribe", make_transcribe_node(whisper_model_size))
    graph.add_node(
        "caption_frames",
        make_caption_frames_node(object_store, captioner, max_frames=max_caption_frames),
    )
    graph.add_node("store", make_store_node(session_maker))  # type: ignore[arg-type]

    graph.add_edge(START, "validate")
    graph.add_edge("validate", "extract_frames")

    # fan-out: extract_frames から 3 経路 (検知 OFF 時は 2 経路)
    graph.add_edge("extract_frames", "extract_audio")
    graph.add_edge("extract_audio", "transcribe")
    graph.add_edge("extract_frames", "caption_frames")

    fan_in: list[str] = ["transcribe", "caption_frames"]
    if enable_detection:
        graph.add_node("detect_objects", make_detect_objects_node(object_store))
        graph.add_edge("extract_frames", "detect_objects")
        fan_in.append("detect_objects")

    # fan-in: 全経路の完了を待って store
    graph.add_edge(fan_in, "store")

    # Phase 3: store の後に Qdrant へ segment インデックス
    if segment_index is not None:
        graph.add_node("index", make_index_segments_node(segment_index))
        graph.add_edge("store", "index")
        graph.add_edge("index", END)
    else:
        graph.add_edge("store", END)
    return graph
