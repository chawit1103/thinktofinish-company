#!/usr/bin/env python3
"""Deterministically route structured review changes through native Hermes Kanban."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

TASK_ID = re.compile(r"\bt_[a-z0-9]+\b")


@dataclass(frozen=True)
class ReviewVerdict:
    decision: str
    reviewed_commit: str
    findings: tuple[str, ...]


def parse_review_verdict(comment: str) -> ReviewVerdict | None:
    try:
        raw = json.loads(comment)["ttf_review"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    decision = raw.get("decision")
    commit = raw.get("reviewed_commit")
    findings = raw.get("findings")
    if decision not in {"approved", "changes_requested"} or not isinstance(commit, str) or not commit:
        return None
    if not isinstance(findings, list) or not all(isinstance(item, str) and item.strip() for item in findings):
        return None
    if decision == "changes_requested" and not findings:
        return None
    return ReviewVerdict(decision=decision, reviewed_commit=commit, findings=tuple(findings))


def remediation_body(review_id: str, verdict: ReviewVerdict) -> str:
    findings = "\n".join(f"- {item}" for item in verdict.findings)
    return (
        f"Remediate the independent review `{review_id}` for commit `{verdict.reviewed_commit}`.\n\n"
        f"Required findings:\n{findings}\n\n"
        "Work only in the declared workspace. Add deterministic regression coverage, run the task's verification commands, "
        "commit a clean handoff, and complete this producer with structured evidence. Do not push main, deploy, use real data, "
        "or bypass the follow-up independent review."
    )


def command(board: str, home: str, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["hermes", "kanban", "--board", board, *args],
        check=True,
        text=True,
        capture_output=capture,
        env={**os.environ, "HERMES_HOME": home},
    )
    return result.stdout


def task_id(output: str) -> str:
    match = TASK_ID.search(output)
    if not match:
        raise RuntimeError(f"Hermes did not return a task id: {output!r}")
    return match.group(0)


def latest_verdict(conn: sqlite3.Connection, review_id: str):
    rows = conn.execute("SELECT body FROM task_comments WHERE task_id=? ORDER BY id DESC", (review_id,)).fetchall()
    for (body,) in rows:
        verdict = parse_review_verdict(body)
        if verdict:
            return verdict
    return None


def workspace(task: sqlite3.Row) -> str:
    path = task["workspace_path"]
    return f"dir:{path}" if path else "scratch"


def reconcile(board: str, home: str, dry_run: bool) -> list[str]:
    db_path = Path(home) / "kanban" / "boards" / board / "kanban.db"
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        reviews = conn.execute(
            "SELECT * FROM tasks WHERE status='blocked' AND assignee='qa-reviewer' ORDER BY id"
        ).fetchall()
        planned: list[tuple[sqlite3.Row, sqlite3.Row, tuple[str, ...], object]] = []
        for review in reviews:
            verdict = latest_verdict(conn, review["id"])
            if not verdict or verdict.decision != "changes_requested":
                continue
            parents = conn.execute(
                "SELECT p.* FROM task_links l JOIN tasks p ON p.id=l.parent_id WHERE l.child_id=?", (review["id"],)
            ).fetchall()
            if len(parents) != 1:
                continue
            children = tuple(row[0] for row in conn.execute("SELECT child_id FROM task_links WHERE parent_id=?", (review["id"],)))
            planned.append((review, parents[0], children, verdict))

    completed: list[str] = []
    for review, producer, children, verdict in planned:
        key = f"ttf-remediation-{review['id']}"
        if dry_run:
            completed.append(f"would remediate {review['id']} and rewire {len(children)} downstream tasks")
            continue
        remediation = task_id(command(
            board,
            home,
            "create",
            f"Remediate review findings from {review['id']}",
            "--body", remediation_body(review["id"], verdict),
            "--assignee", producer["assignee"],
            "--workspace", workspace(producer),
            "--idempotency-key", key,
            "--json",
            capture=True,
        ))
        follow_up = task_id(command(
            board,
            home,
            "create",
            f"Independent re-review of {remediation}",
            "--body", f"Read-only review of remediation task {remediation}. Verify every finding from {review['id']} is resolved and return a structured ttf_review verdict.",
            "--assignee", review["assignee"],
            "--parent", remediation,
            "--workspace", workspace(producer),
            "--idempotency-key", f"ttf-rereview-{review['id']}",
            "--json",
            capture=True,
        ))
        for child in children:
            command(board, home, "unlink", review["id"], child)
            command(board, home, "link", follow_up, child)
        command(board, home, "archive", review["id"])
        completed.append(f"remediated {review['id']} -> {remediation} -> {follow_up}")
    return completed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board")
    parser.add_argument("--home", default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        verdict = parse_review_verdict('{"ttf_review":{"decision":"changes_requested","reviewed_commit":"abc1234","findings":["Add a regression test"]}}')
        assert verdict and "Add a regression test" in remediation_body("t_review", verdict)
        assert parse_review_verdict("REQUEST_CHANGES") is None
        assert parse_review_verdict('{"ttf_review":{"decision":"changes_requested","reviewed_commit":"abc1234","findings":[]}}') is None
        print("self-test passed")
        return 0
    if not args.board:
        parser.error("--board is required unless --self-test is used")
    for result in reconcile(args.board, args.home, args.dry_run):
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
