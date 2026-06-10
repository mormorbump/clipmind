"""評価データセットの定義とロード (M4-1).

形式: JSONL. 1 行 = 1 クエリ.

    {"query": "When does the presenter show Q3 results?",
     "video_id": "<uuid>",
     "relevant_start_ms": [315000, 320000]}

`relevant_start_ms` は「正解とみなす segment 窓の start_ms」のリスト.
segment の窓幅 (5 秒) と合わせて人手でラベル付けする.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalQuery:
    """評価クエリ 1 件."""

    query: str
    video_id: str
    relevant_start_ms: tuple[int, ...]


def load_dataset(path: Path) -> list[EvalQuery]:
    """JSONL から評価クエリ列を読み込む."""
    queries: list[EvalQuery] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
            queries.append(
                EvalQuery(
                    query=str(obj["query"]),
                    video_id=str(obj["video_id"]),
                    relevant_start_ms=tuple(int(v) for v in obj["relevant_start_ms"]),
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            msg = f"{path}:{line_no}: invalid eval entry: {e}"
            raise ValueError(msg) from e
    return queries
