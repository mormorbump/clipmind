"""Ingest グラフの組み立て + Checkpointer 付き実行ヘルパ.

`run_ingest()` は API ハンドラ / CLI / e2e テストから共通で呼ぶ.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from clipmind.graph.ingest_graph import build_ingest_graph
from clipmind.graph.state import (
    Caption,
    DetectionRecord,
    Frame,
    IngestState,
    TranscriptSegment,
)
from clipmind.ingest.progress import NullProgressPublisher, ProgressPublisher
from clipmind.llm.captioner import Captioner, NullCaptioner

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from clipmind.rag.indexer import SegmentIndex
    from clipmind.storage.object_store import ObjectStore


async def run_ingest(
    *,
    video_id: str,
    video_path: Path,
    object_store: ObjectStore,
    audio_dir: Path,
    checkpoint_db_path: Path,
    session_maker: async_sessionmaker[AsyncSession],
    captioner: Captioner | None = None,
    segment_index: SegmentIndex | None = None,
    progress: ProgressPublisher | None = None,
    whisper_model_size: str = "base",
    enable_detection: bool = True,
    max_caption_frames: int | None = 20,
) -> IngestState:
    """Ingest グラフを Checkpointer 付きで実行し、最終 State を返す.

    Args:
        video_id: 文字列化された UUID. store ノードでこのキーで Video レコードを更新.
        video_path: 入力動画ファイル
        object_store: フレーム JPEG の保存先
        audio_dir: ffmpeg 出力 wav の保存先
        checkpoint_db_path: SqliteSaver の SQLite ファイルパス
        session_maker: store ノード用の DB セッション factory
        captioner: None なら NullCaptioner (キャプションなしで継続)
        whisper_model_size: faster-whisper のモデルサイズ
        enable_detection: YOLO 検知経路の有効化
        max_caption_frames: キャプション対象フレーム数上限
    """
    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    builder = build_ingest_graph(
        object_store=object_store,
        audio_dir=audio_dir,
        session_maker=session_maker,
        captioner=captioner if captioner is not None else NullCaptioner(),
        segment_index=segment_index,
        whisper_model_size=whisper_model_size,
        enable_detection=enable_detection,
        max_caption_frames=max_caption_frames,
    )

    initial_state: IngestState = {
        "video_id": video_id,
        "source": "local",
        "video_path": str(video_path),
        "audio_path": None,
        "frames": cast("list[Frame]", []),
        "transcripts": cast("list[TranscriptSegment]", []),
        "detections": cast("list[DetectionRecord]", []),
        "captions": cast("list[Caption]", []),
        "errors": cast("list[str]", []),
    }

    publisher: ProgressPublisher = progress if progress is not None else NullProgressPublisher()

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_db_path)) as saver:
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": f"ingest-{video_id}"}}
        # stream_mode="updates" でノード完了ごとにイベントが来る → 進捗発行 (M8-1)
        # LangGraph 1.2 の astream は overload が複雑で config=dict の推論が効かないため抑止.
        final_state: dict[str, object] = dict(initial_state)
        async for update in graph.astream(  # type: ignore[call-overload]
            initial_state, config=config, stream_mode="updates"
        ):
            for node_name, node_output in update.items():
                if isinstance(node_output, dict):
                    final_state.update(node_output)
                await publisher.publish(video_id, node_name)
        await publisher.publish(video_id, "completed")

        # astream の updates は「差分」なので、確定 State は checkpointer から取り直す
        snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
        result = snapshot.values if snapshot.values else final_state
    return cast("IngestState", result)
