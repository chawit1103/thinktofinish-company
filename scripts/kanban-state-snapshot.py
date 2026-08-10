#!/usr/bin/env python3
"""Emit a stable board snapshot for Hermes cron monitor mode."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True)
    parser.add_argument("--home", default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    args = parser.parse_args()
    db_path = Path(args.home) / "kanban" / "boards" / args.board / "kanban.db"
    if not db_path.is_file():
        raise SystemExit(f"Kanban database not found: {db_path}")
    query = """
    SELECT t.id,t.status,t.assignee,COALESCE(t.block_kind,''),COALESCE(r.outcome,''),COALESCE(r.summary,'')
    FROM tasks t LEFT JOIN task_runs r ON r.id=(SELECT id FROM task_runs WHERE task_id=t.id ORDER BY id DESC LIMIT 1)
    WHERE t.status NOT IN ('done','archived') ORDER BY t.id
    """
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        fields = ("id", "status", "assignee", "block_kind", "outcome", "summary")
        rows = [dict(zip(fields, row)) for row in conn.execute(query)]
    print(json.dumps({"board": args.board, "tasks": rows}, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
