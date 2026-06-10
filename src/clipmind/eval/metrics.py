"""Retrieval 評価メトリクス (M4-2).

すべて「ランク順の予測リスト」と「正解集合」を受け取る純関数.
予測・正解の要素は hashable なら何でもよい (ClipMind では (video_id, start_ms) タプル).
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence


def recall_at_k(ranked: Sequence[Hashable], relevant: set[Hashable], k: int) -> float:
    """上位 k 件に正解がどれだけ含まれるか (0..1).

    relevant が空なら 0.0 (定義不能ケースはスコアに含めない運用を推奨).
    """
    if not relevant:
        return 0.0
    top = set(ranked[:k])
    return len(top & relevant) / len(relevant)


def mrr(ranked: Sequence[Hashable], relevant: set[Hashable]) -> float:
    """Mean Reciprocal Rank の 1 クエリ分 (= Reciprocal Rank).

    最初に正解が出てきた順位 r に対して 1/r. 正解が出なければ 0.
    """
    for i, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[Hashable], relevant: set[Hashable], k: int) -> float:
    """nDCG@k (二値関連度).

    DCG = Σ rel_i / log2(i+1)、IDCG は正解を上位に並べた理想値.
    """
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(i + 1) for i, item in enumerate(ranked[:k], start=1) if item in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0
