"""caption_frames ノード: キーフレームをマルチモーダル LLM でキャプション.

API キーが無い環境では NullCaptioner が None を返し、キャプションなしで継続する.
1 フレームの失敗で全体を止めない (部分失敗時の Ingest 継続, ADR-0003).
"""

from __future__ import annotations

from clipmind.graph.state import Caption, IngestState
from clipmind.llm.captioner import Captioner
from clipmind.storage.object_store import ObjectStore


def make_caption_frames_node(  # type: ignore[no-untyped-def]
    object_store: ObjectStore,
    captioner: Captioner,
    *,
    max_frames: int | None = None,
):
    """`captioner` でフレームを説明文化するノードを返す.

    Args:
        max_frames: コスト制御. None なら全キーフレーム対象.
    """

    async def caption_frames_node(state: IngestState) -> IngestState:
        frames = state.get("frames", [])
        if max_frames is not None:
            frames = frames[:max_frames]
        if not frames:
            return {}

        captions: list[Caption] = []
        errors: list[str] = []
        for frame in frames:
            try:
                jpeg = await object_store.get(frame["object_store_key"])
                result = await captioner.caption(jpeg)
            except Exception as e:
                errors.append(f"caption_frames: frame {frame['index']}: {e}")
                continue
            if result is None:
                # NullCaptioner (キー無し): キャプション全スキップ
                return {}
            captions.append(
                Caption(frame_index=frame["index"], text=result.text, model=result.model)
            )

        out: IngestState = {"captions": captions}
        if errors:
            out["errors"] = errors
        return out

    return caption_frames_node
