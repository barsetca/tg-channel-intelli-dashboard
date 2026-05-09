from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _get_audit_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()
    return int(row[0] if row else 0)


def _tail_audit_rows(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, audit_kind, status, quality_gate_json, error_text, result_summary_json, created_at
            FROM audit_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": int(r["id"]),
                "audit_kind": r["audit_kind"],
                "status": r["status"],
                "quality_gate_json": r["quality_gate_json"],
                "error_text": r["error_text"],
                "result_summary_json": r["result_summary_json"],
                "created_at": r["created_at"],
            }
        )
    return out


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    queries_file = repo_root / "tests_data" / "queries.jsonl"
    db_path = Path(
        os.getenv(
            "ACCEPTANCE_DB_PATH",
            str(repo_root / "backend" / "data" / "app.db"),
        )
    )
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    out_path = repo_root / "docs" / "acceptance" / "smoke_audit_snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not queries_file.exists():
        raise SystemExit(f"Missing file: {queries_file}")
    if not db_path.exists():
        raise SystemExit(f"Missing SQLite DB: {db_path}")

    rows = _read_jsonl(queries_file)
    before = _get_audit_count(db_path)
    run_results: list[dict[str, Any]] = []

    for idx, item in enumerate(rows, start=1):
        body = {
            "topic": str(item["query"]),
            "count": 10,
            "search_source": "saved_catalog",
            "channel_type": "all",
            "language": "ru",
        }
        req = urlrequest.Request(
            f"{api_base}/api/v1/search-channels",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=60) as resp:
                status_code = int(resp.getcode())
                raw = resp.read().decode("utf-8")
                data = json.loads(raw or "{}")
        except urlerror.HTTPError as exc:
            status_code = int(exc.code)
            data = {"detail": exc.read().decode("utf-8")}
        except urlerror.URLError as exc:
            raise SystemExit(
                f"API is unavailable at {api_base}. Start backend first. Details: {exc}"
            ) from exc

        ok = status_code == 200
        if not isinstance(data, dict):
            data = {"detail": str(data)}
        manual = data.get("manual_review") if isinstance(data, dict) else None
        needs_review = bool(manual and manual.get("needs_review"))
        reason = (manual or {}).get("reason")
        channels_count = len(data.get("channels", [])) if isinstance(data, dict) else 0
        print(
            f"{idx:02d}. status={status_code} needs_review={needs_review} "
            f"channels={channels_count} query={str(item['query'])[:70]}"
        )
        run_results.append(
            {
                "index": idx,
                "query": item["query"],
                "expected_needs_review": bool(item["expected_needs_review"]),
                "actual_needs_review": needs_review,
                "reason": reason,
                "status_code": status_code,
                "channels_count": channels_count,
            }
        )

    after = _get_audit_count(db_path)
    mismatches = [
        r for r in run_results if bool(r["expected_needs_review"]) != bool(r["actual_needs_review"])
    ]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "queries_file": str(queries_file.relative_to(repo_root)),
        "db_path": str(db_path),
        "api_base_url": api_base,
        "audit_runs_before": before,
        "audit_runs_after": after,
        "audit_runs_added": after - before,
        "requirement_check": {
            "audit_runs_total_ge_10": after >= 10,
            "audit_runs_added_ge_10": (after - before) >= 10,
            "needs_review_matches_expected": len(mismatches) == 0,
        },
        "query_results": run_results,
        "needs_review_mismatches": mismatches,
        "latest_audit_runs": _tail_audit_rows(db_path, limit=20),
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved snapshot: {out_path}")
    print(f"audit_runs before={before}, after={after}, added={after - before}")
    print(f"needs_review mismatches={len(mismatches)}")


if __name__ == "__main__":
    main()
