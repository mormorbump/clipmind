"""Retrieval メトリクスの unit テスト (手計算と一致することを確認)."""

from __future__ import annotations

import math

from clipmind.eval.metrics import mrr, ndcg_at_k, recall_at_k


def test_recall_at_k() -> None:
    ranked = ["a", "b", "c", "d", "e"]
    assert recall_at_k(ranked, {"a", "c"}, k=5) == 1.0
    assert recall_at_k(ranked, {"a", "z"}, k=5) == 0.5
    assert recall_at_k(ranked, {"z"}, k=5) == 0.0
    assert recall_at_k(ranked, {"e"}, k=3) == 0.0  # k で切られる
    assert recall_at_k(ranked, set(), k=5) == 0.0  # 正解空


def test_mrr() -> None:
    assert mrr(["a", "b", "c"], {"a"}) == 1.0
    assert mrr(["a", "b", "c"], {"b"}) == 0.5
    assert mrr(["a", "b", "c"], {"c"}) == 1 / 3
    assert mrr(["a", "b", "c"], {"z"}) == 0.0
    # 複数正解: 最初に出た方
    assert mrr(["a", "b", "c"], {"b", "c"}) == 0.5


def test_ndcg_at_k() -> None:
    # 正解 1 件が 1 位 → 理想形 = 1.0
    assert ndcg_at_k(["a", "b"], {"a"}, k=5) == 1.0
    # 正解 1 件が 2 位: DCG = 1/log2(3), IDCG = 1/log2(2) = 1
    expected = (1 / math.log2(3)) / 1.0
    assert abs(ndcg_at_k(["x", "a"], {"a"}, k=5) - expected) < 1e-9
    # 正解なし
    assert ndcg_at_k(["x", "y"], {"a"}, k=5) == 0.0
    assert ndcg_at_k([], set(), k=5) == 0.0


def test_ndcg_multiple_relevant_perfect_order() -> None:
    # 2 件の正解が 1,2 位 → 1.0
    assert abs(ndcg_at_k(["a", "b", "x"], {"a", "b"}, k=5) - 1.0) < 1e-9
