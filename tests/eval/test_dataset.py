"""評価データセットローダーのテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from clipmind.eval.dataset import load_dataset


def test_load_dataset_parses_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "ds.jsonl"
    p.write_text(
        "# comment line\n"
        '{"query": "q1", "video_id": "v1", "relevant_start_ms": [0, 5000]}\n'
        "\n"
        '{"query": "q2", "video_id": "v2", "relevant_start_ms": [10000]}\n',
        encoding="utf-8",
    )
    queries = load_dataset(p)
    assert len(queries) == 2
    assert queries[0].query == "q1"
    assert queries[0].relevant_start_ms == (0, 5000)


def test_load_dataset_rejects_broken_line(tmp_path: Path) -> None:
    p = tmp_path / "broken.jsonl"
    p.write_text('{"query": "q1"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid eval entry"):
        load_dataset(p)
