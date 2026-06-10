"""Ingest StateGraph 構築.

Phase 1 の流れ: validate → extract_frames → extract_audio → transcribe → store
並列ノードは Phase 2 で追加する (architecture.md §3.2 参照).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from clipmind.graph.nodes.extract_audio import make_extract_audio_node
from clipmind.graph.nodes.extract_frames import make_extract_frames_node
from clipmind.graph.nodes.store import make_store_node
from clipmind.graph.nodes.transcribe import make_transcribe_node
from clipmind.graph.nodes.validate import validate_input
from clipmind.graph.state import IngestState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
    whisper_model_size: str = "base",
) -> StateGraph[IngestState, None, IngestState, IngestState]:
    """Phase 1 の完全な Ingest グラフを返す (compile 前).

    `store` の `# type: ignore[arg-type]` は LangGraph 1.2 の `add_node` が
    `_Node[Never]` を期待する型ナローイング問題への対処. ランタイム挙動には影響しない.
    """
    graph: StateGraph[IngestState, None, IngestState, IngestState] = StateGraph(IngestState)
    graph.add_node("validate", validate_input)
    graph.add_node("extract_frames", make_extract_frames_node(object_store))
    graph.add_node("extract_audio", make_extract_audio_node(audio_dir))
    graph.add_node("transcribe", make_transcribe_node(whisper_model_size))
    graph.add_node("store", make_store_node(session_maker))  # type: ignore[arg-type]

    graph.add_edge(START, "validate")
    graph.add_edge("validate", "extract_frames")
    graph.add_edge("extract_frames", "extract_audio")
    graph.add_edge("extract_audio", "transcribe")
    graph.add_edge("transcribe", "store")
    graph.add_edge("store", END)
    return graph
