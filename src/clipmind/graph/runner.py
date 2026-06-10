"""Ingest グラフの組み立て + Checkpointer 付き実行ヘルパ.

`run_ingest()` は API ハンドラ / CLI / e2e テストから共通で呼ぶ.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from clipmind.graph.ingest_graph import build_ingest_graph
from clipmind.graph.state import Frame, IngestState, TranscriptSegment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from clipmind.storage.object_store import ObjectStore


async def run_ingest(
    *,
    video_id: str,
    video_path: Path,
    object_store: ObjectStore,
    audio_dir: Path,
    checkpoint_db_path: Path,
    session_maker: async_sessionmaker[AsyncSession],
    whisper_model_size: str = "base",
) -> IngestState:
    """Ingest グラフを Checkpointer 付きで実行し、最終 State を返す.

    Args:
        video_id: 文字列化された UUID. store ノードでこのキーで Video レコードを更新.
        video_path: 入力動画ファイル
        object_store: フレーム JPEG の保存先
        audio_dir: ffmpeg 出力 wav の保存先
        checkpoint_db_path: SqliteSaver の SQLite ファイルパス
        session_maker: store ノード用の DB セッション factory
        whisper_model_size: faster-whisper のモデルサイズ
    """
    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    builder = build_ingest_graph(
        object_store=object_store,
        audio_dir=audio_dir,
        session_maker=session_maker,
        whisper_model_size=whisper_model_size,
    )

    initial_state: IngestState = {
        "video_id": video_id,
        "source": "local",
        "video_path": str(video_path),
        "audio_path": None,
        "frames": cast("list[Frame]", []),
        "transcripts": cast("list[TranscriptSegment]", []),
        "errors": cast("list[str]", []),
    }

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_db_path)) as saver:
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": f"ingest-{video_id}"}}
        # LangGraph 1.2 の Pregel.ainvoke は overload が複雑で `config=dict` の引数推論が
        # 効きづらい. 動作上は正しい呼び出しなので type: ignore で抑止.
        result = await graph.ainvoke(initial_state, config=config)  # type: ignore[call-overload]
    return cast("IngestState", result)
