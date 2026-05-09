from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

def _load_rows() -> list[dict]:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "tests_data" / "queries.jsonl"
    assert src.exists(), "Missing tests_data/queries.jsonl"

    rows: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def test_queries_jsonl_contract() -> None:
    rows = _load_rows()

    assert len(rows) == 10, "queries.jsonl must contain exactly 10 test queries"

    required = {"dataset_name", "query", "expected_needs_review", "kind", "why"}
    for row in rows:
        assert required.issubset(row.keys())
        assert isinstance(row["query"], str) and row["query"].strip()
        assert isinstance(row["expected_needs_review"], bool)
        assert row["kind"] in {"correct", "ambiguous", "impossible"}
        assert isinstance(row["why"], str) and row["why"].strip()

    by_kind = Counter(str(r["kind"]) for r in rows)
    assert by_kind["correct"] == 7
    assert by_kind["ambiguous"] == 2
    assert by_kind["impossible"] == 1

    by_review = Counter(bool(r["expected_needs_review"]) for r in rows)
    assert by_review[False] == 7
    assert by_review[True] == 3


@pytest.mark.parametrize(
    "idx,row",
    [(i + 1, r) for i, r in enumerate(_load_rows())],
    ids=lambda x: f"case_{x}" if isinstance(x, int) else str(x.get("kind", "row")),
)
def test_queries_jsonl_each_case(idx: int, row: dict) -> None:
    assert isinstance(row["query"], str) and row["query"].strip()
    assert isinstance(row["expected_needs_review"], bool)
    assert row["kind"] in {"correct", "ambiguous", "impossible"}
    print(
        f"{idx:02d}. PASS | kind={row['kind']} | "
        f"expected_needs_review={row['expected_needs_review']} | "
        f"query={row['query'][:80]}"
    )
