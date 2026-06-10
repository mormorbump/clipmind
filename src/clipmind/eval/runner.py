"""Retrieval 評価ランナー (M4-2).

dense / hybrid の両モードで dataset を評価し、Markdown レポートを生成する.

CLI:
    uv run python -m clipmind.eval.runner --dataset eval/dataset.jsonl \
        --output .data/eval-report.md
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from clipmind.eval.dataset import EvalQuery, load_dataset
from clipmind.eval.metrics import mrr, ndcg_at_k, recall_at_k
from clipmind.rag.indexer import SegmentIndex


@dataclass
class ModeResult:
    """1 検索モードの集計結果."""

    mode: str
    recall_at_5: float = 0.0
    mrr_score: float = 0.0
    ndcg_at_5: float = 0.0
    per_query: list[dict[str, object]] = field(default_factory=list)


@dataclass
class EvalReport:
    """評価レポート全体."""

    dataset_size: int
    results: list[ModeResult]

    def to_markdown(self) -> str:
        lines = [
            "# Retrieval Evaluation Report",
            "",
            f"- queries: {self.dataset_size}",
            "",
            "| mode | Recall@5 | MRR | nDCG@5 |",
            "|---|---|---|---|",
        ]
        lines.extend(
            f"| {r.mode} | {r.recall_at_5:.3f} | {r.mrr_score:.3f} | {r.ndcg_at_5:.3f} |"
            for r in self.results
        )
        lines.append("")
        for r in self.results:
            lines.append(f"## {r.mode} — per query")
            lines.append("")
            lines.append("| query | Recall@5 | RR | nDCG@5 |")
            lines.append("|---|---|---|---|")
            for q in r.per_query:
                row = (
                    f"| {q['query']} | {q['recall_at_5']:.2f} "
                    f"| {q['rr']:.2f} | {q['ndcg_at_5']:.2f} |"
                )
                lines.append(row)
            lines.append("")
        return "\n".join(lines)


async def evaluate_mode(
    index: SegmentIndex, queries: list[EvalQuery], *, mode: str, top_k: int = 5
) -> ModeResult:
    """1 モードで全クエリを評価."""
    result = ModeResult(mode=mode)
    recalls: list[float] = []
    rrs: list[float] = []
    ndcgs: list[float] = []

    for q in queries:
        if mode == "dense":
            hits = await index.search_dense(q.query, top_k=top_k, video_id=q.video_id)
        else:
            hits = await index.search_hybrid(q.query, top_k=top_k, video_id=q.video_id)

        ranked = [h.start_ms for h in hits]
        relevant: set[object] = set(q.relevant_start_ms)

        r = recall_at_k(ranked, relevant, top_k)
        rr = mrr(ranked, relevant)
        n = ndcg_at_k(ranked, relevant, top_k)
        recalls.append(r)
        rrs.append(rr)
        ndcgs.append(n)
        result.per_query.append({"query": q.query, "recall_at_5": r, "rr": rr, "ndcg_at_5": n})

    count = len(queries) or 1
    result.recall_at_5 = sum(recalls) / count
    result.mrr_score = sum(rrs) / count
    result.ndcg_at_5 = sum(ndcgs) / count
    return result


async def run_evaluation(
    index: SegmentIndex, queries: list[EvalQuery], *, modes: tuple[str, ...] = ("dense", "hybrid")
) -> EvalReport:
    """全モードで評価してレポートを返す."""
    results = [await evaluate_mode(index, queries, mode=m) for m in modes]
    return EvalReport(dataset_size=len(queries), results=results)


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval evaluation")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".data/eval-report.md"))
    args = parser.parse_args()

    from clipmind.config import get_settings
    from clipmind.rag.factory import build_segment_index

    queries = load_dataset(args.dataset)
    index = build_segment_index(get_settings())
    try:
        report = await run_evaluation(index, queries)
    finally:
        await index.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.to_markdown(), encoding="utf-8")
    print(report.to_markdown())
    print(f"\nreport written to {args.output}")


if __name__ == "__main__":
    asyncio.run(_main())
