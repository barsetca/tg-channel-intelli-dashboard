from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "tests_data" / "queries.jsonl"
    if not src.exists():
        raise SystemExit(f"File not found: {src}")

    rows: list[dict] = []
    for idx, line in enumerate(src.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Line {idx}: invalid JSON: {exc}") from exc
        rows.append(row)

    if len(rows) != 10:
        raise SystemExit(f"Expected 10 rows, got {len(rows)}")

    required = {"dataset_name", "query", "expected_needs_review", "kind", "why"}
    print("Detailed per-test results:")
    for idx, row in enumerate(rows, start=1):
        missing = sorted(required - set(row.keys()))
        if missing:
            raise SystemExit(f"Line {idx}: missing keys {missing}")
        if not isinstance(row["query"], str) or len(row["query"].strip()) < 3:
            raise SystemExit(f"Line {idx}: query must be non-empty string")
        if not isinstance(row["expected_needs_review"], bool):
            raise SystemExit(f"Line {idx}: expected_needs_review must be bool")
        if row["kind"] not in {"correct", "ambiguous", "impossible"}:
            raise SystemExit(f"Line {idx}: kind must be correct|ambiguous|impossible")
        print(
            f"{idx:02d}. PASS | kind={row['kind']} | "
            f"expected_needs_review={row['expected_needs_review']} | query={row['query'][:80]}"
        )

    by_kind = Counter(str(r["kind"]) for r in rows)
    if by_kind["correct"] != 7 or by_kind["ambiguous"] != 2 or by_kind["impossible"] != 1:
        raise SystemExit(f"Expected distribution 7/2/1, got {dict(by_kind)}")

    by_review = Counter(bool(r["expected_needs_review"]) for r in rows)
    if by_review[False] != 7 or by_review[True] != 3:
        raise SystemExit(f"Expected needs_review distribution 7 false / 3 true, got {dict(by_review)}")

    print("queries.jsonl validation passed")
    print(f"rows={len(rows)} kinds={dict(by_kind)} needs_review={dict(by_review)}")


if __name__ == "__main__":
    main()
