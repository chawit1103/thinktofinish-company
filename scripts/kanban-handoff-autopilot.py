#!/usr/bin/env python3
"""Advance verified non-goal producer handoffs to independent review."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path

COMMIT = re.compile(r"\bcommit\s+[0-9a-f]{7,64}\b", re.IGNORECASE)
VERIFICATION = re.compile(r"\b(?:pass(?:ed)?|success(?:ful(?:ly)?)?|succeeded|verified)\b", re.IGNORECASE)


def eligible(summary: str | None, reviewer_count: int) -> bool:
    return bool(summary and summary.lstrip().lower().startswith("review-required:") and COMMIT.search(summary) and VERIFICATION.search(summary) and reviewer_count)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board")
    parser.add_argument("--home", default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        assert eligible("review-required: commit abcdef1; pytest passed", 1)
        assert not eligible("review-required: pytest passed", 1)
        assert not eligible("review-required: commit abcdef1; pytest ran", 1)
        assert not eligible("review-required: abcdef1; pytest passed", 1)
        assert not eligible("review-required: commit abcdef1", 0)
        print("self-test passed")
        return 0
    if not args.board:
        parser.error("--board is required unless --self-test is used")
    db_path = Path(args.home) / "kanban" / "boards" / args.board / "kanban.db"
    if not db_path.is_file():
        raise SystemExit(f"Kanban database not found: {db_path}")
    query = """
    SELECT t.id, COALESCE(r.summary, '') FROM tasks AS t
    JOIN task_runs AS r ON r.id = (SELECT id FROM task_runs WHERE task_id=t.id ORDER BY id DESC LIMIT 1)
    WHERE t.status='blocked' AND t.block_kind='needs_input' AND COALESCE(t.goal_mode, 0)=0
    """
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(query).fetchall()
        for task_id, summary in rows:
            reviewers = conn.execute(
                "SELECT COUNT(*) FROM task_links l JOIN tasks c ON c.id=l.child_id WHERE l.parent_id=? AND c.assignee='qa-reviewer' AND c.status IN ('todo','ready','running','blocked')",
                (task_id,),
            ).fetchone()[0]
            if not eligible(summary, reviewers):
                continue
            if args.dry_run:
                print(f"would complete {args.board}/{task_id} -> independent review")
                continue
            metadata = json.dumps({"autopilot_transition": "producer_to_independent_review"})
            subprocess.run(
                ["hermes", "kanban", "--board", args.board, "complete", task_id, "--summary", summary, "--metadata", metadata],
                check=True,
            )
            print(f"completed {args.board}/{task_id} -> independent review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
