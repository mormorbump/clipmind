"""Checkpointer resume 実験 (Phase 1 DoD の学習項目).

シナリオ:
  extract (重い処理のつもり) → flaky (1 回目は必ず死ぬ = Whisper OOM 想定) → store

1 回目の invoke: flaky で例外 → graph 失敗。ただし extract の結果は checkpoint 済み.
2 回目の invoke: 同じ thread_id + input=None で resume → extract は再実行されず flaky から続行.

実行: uv run python .context/experiment_checkpoint_resume.py
"""

from __future__ import annotations

import asyncio
import tempfile
from operator import add
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

EXTRACT_CALLS = 0
FLAKY_CALLS = 0


class S(TypedDict, total=False):
    video_id: str
    frames: Annotated[list[str], add]
    transcripts: Annotated[list[str], add]


async def extract(state: S) -> S:
    global EXTRACT_CALLS
    EXTRACT_CALLS += 1
    print(f"  [extract] 実行 {EXTRACT_CALLS} 回目 (重い処理のつもり)")
    return {"frames": [f"frame-{i}" for i in range(3)]}


async def flaky_transcribe(state: S) -> S:
    global FLAKY_CALLS
    FLAKY_CALLS += 1
    if FLAKY_CALLS == 1:
        print("  [flaky_transcribe] 1 回目 → 故意に死ぬ (Whisper OOM 想定)")
        raise RuntimeError("simulated whisper OOM")
    print(f"  [flaky_transcribe] {FLAKY_CALLS} 回目 → 成功")
    return {"transcripts": ["hello world"]}


async def main() -> None:
    g: StateGraph = StateGraph(S)
    g.add_node("extract", extract)
    g.add_node("transcribe", flaky_transcribe)
    g.add_edge(START, "extract")
    g.add_edge("extract", "transcribe")
    g.add_edge("transcribe", END)

    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "ckpt.db"
        async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
            graph = g.compile(checkpointer=saver)
            config = {"configurable": {"thread_id": "demo"}}

            print("--- 1 回目の invoke (失敗するはず) ---")
            try:
                await graph.ainvoke({"video_id": "vid", "frames": [], "transcripts": []}, config)
            except RuntimeError as e:
                print(f"  graph 失敗: {e}")

            state = await graph.aget_state(config)
            print(f"  checkpoint 済み frames: {state.values.get('frames')}")
            print(f"  next (再開地点): {state.next}")

            print("--- 2 回目の invoke (input=None で resume) ---")
            result = await graph.ainvoke(None, config)
            print(f"  最終 transcripts: {result.get('transcripts')}")

    print("--- 検証 ---")
    print(f"  extract 実行回数: {EXTRACT_CALLS} (1 なら resume 成功 = 再実行されていない)")
    print(f"  flaky  実行回数: {FLAKY_CALLS}")
    assert EXTRACT_CALLS == 1, "resume で extract が再実行された!"
    assert FLAKY_CALLS == 2
    print("  ✅ Checkpointer resume 動作確認 OK")


if __name__ == "__main__":
    asyncio.run(main())
