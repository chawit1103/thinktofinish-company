#!/usr/bin/env python3
"""Atomically route structured review changes through Hermes Kanban."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

BOARD_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
GIT_COMMIT = re.compile(r"[0-9a-fA-F]{7,64}")
MAX_REMEDIATION_GENERATIONS = 3
ENGINE_AUTHOR = "ttf-transition-engine"
LOCK_BUSY = "transition engine already running"


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
    if not isinstance(raw, dict):
        return None
    decision = raw.get("decision")
    commit = raw.get("reviewed_commit")
    findings = raw.get("findings")
    if (
        decision not in {"approved", "changes_requested"}
        or not isinstance(commit, str)
        or not GIT_COMMIT.fullmatch(commit)
    ):
        return None
    if (
        not isinstance(findings, list)
        or len(findings) > 50
        or not all(isinstance(item, str) and item.strip() and len(item) <= 2000 for item in findings)
    ):
        return None
    if decision == "changes_requested" and not findings:
        return None
    return ReviewVerdict(decision=decision, reviewed_commit=commit, findings=tuple(findings))


def findings_text(verdict: ReviewVerdict) -> str:
    return "\n".join(f"- {item}" for item in verdict.findings)


def remediation_body(review_id: str, producer_id: str, verdict: ReviewVerdict) -> str:
    return (
        f"Remediate the independent review `{review_id}` for commit `{verdict.reviewed_commit}`.\n\n"
        f"Required findings:\n{findings_text(verdict)}\n\n"
        f"Original producer task: `{producer_id}`. Read its full task contract, acceptance criteria, requirement IDs, "
        "completion evidence, and verification commands before editing. Revalidate the complete original contract, not only "
        "the listed findings.\n\n"
        "Work only in the declared workspace. Add deterministic regression coverage, run the task's verification commands, "
        "commit a clean handoff, and complete this producer with structured evidence. Do not push main, deploy, use real data, "
        "or bypass the follow-up independent review."
    )


def rereview_body(review_id: str, producer_id: str, remediation_id: str, verdict: ReviewVerdict) -> str:
    return (
        f"Read-only independent re-review of remediation task `{remediation_id}` for original producer `{producer_id}` and "
        f"rejected review `{review_id}`. The rejected baseline was `{verdict.reviewed_commit}`.\n\n"
        f"Required findings to verify:\n{findings_text(verdict)}\n\n"
        "Resolve the completed remediation handoff commit from its evidence and checkout HEAD; review that new commit, not the "
        "rejected baseline. Read the original producer's full task contract and revalidate every acceptance criterion and "
        "verification command. Return one structured ttf_review verdict whose reviewed_commit is the remediation commit; do "
        "not repair the implementation yourself."
    )


def gate_body(review_id: str, verdict: ReviewVerdict) -> str:
    return (
        f"Autonomous remediation stopped after {MAX_REMEDIATION_GENERATIONS} generations for review `{review_id}` at "
        f"commit `{verdict.reviewed_commit}`.\n\nOutstanding findings:\n{findings_text(verdict)}\n\n"
        "Owner input is required before any further remediation. This card now gates every downstream task; complete it "
        "only after recording the owner's decision and safe next action."
    )


def canonical_board(board: str) -> str:
    value = board.strip().lower()
    if not BOARD_SLUG.fullmatch(value):
        raise ValueError("board must be a 1-64 character Hermes slug")
    return value


def board_db_path(home: str, board: str) -> Path:
    override = os.environ.get("HERMES_KANBAN_DB", "").strip()
    if override:
        return Path(override).expanduser()
    root = Path(home).expanduser()
    slug = canonical_board(board)
    return root / "kanban.db" if slug == "default" else root / "kanban" / "boards" / slug / "kanban.db"


def check_board(home: str, board: str) -> Path:
    db_path = board_db_path(home, board)
    if not db_path.is_file():
        raise FileNotFoundError(f"Kanban board not found: {canonical_board(board)} ({db_path})")
    required = {
        "tasks": {
            "id", "title", "body", "status", "assignee", "created_by", "created_at", "priority",
            "workspace_kind", "workspace_path", "tenant", "idempotency_key", "block_kind",
            "block_recurrences", "claim_lock", "claim_expires", "worker_pid", "current_run_id",
        },
        "task_links": {"parent_id", "child_id"},
        "task_comments": {"id", "task_id", "author", "body"},
        "task_events": {"id", "task_id", "kind", "payload", "created_at"},
        "kanban_notify_subs": {
            "task_id", "platform", "chat_id", "thread_id", "user_id", "notifier_profile",
            "created_at", "last_event_id",
        },
    }
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        for table, columns in required.items():
            present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            missing = sorted(columns - present)
            if missing:
                raise ValueError(
                    f"Kanban board schema is missing {table}.{', '.join(missing)}; open it once with current "
                    f"Hermes (`hermes kanban --board {canonical_board(board)} list`) and retry"
                )
    return db_path


def review_assignee(conn: sqlite3.Connection, review_id: str) -> str | None:
    row = conn.execute("SELECT assignee FROM tasks WHERE id=?", (review_id,)).fetchone()
    value = row[0] if row else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def current_verdict_marker(conn: sqlite3.Connection, review_id: str):
    assignee = review_assignee(conn, review_id)
    if not assignee:
        return None
    rows = conn.execute(
        "SELECT id, author, body FROM task_comments WHERE task_id=? ORDER BY id DESC LIMIT 2", (review_id,)
    ).fetchall()
    if not rows:
        return None
    verdict = parse_review_verdict(rows[0][2]) if rows[0][1] == assignee else None
    if verdict:
        return verdict, rows[0][0]
    if (
        len(rows) == 2
        and rows[0][1] == assignee
        and str(rows[0][2]).startswith("BLOCKED:")
        and rows[1][1] == assignee
    ):
        verdict = parse_review_verdict(rows[1][2])
        return (verdict, rows[0][0]) if verdict else None
    return None


def latest_verdict(conn: sqlite3.Connection, review_id: str):
    marked = current_verdict_marker(conn, review_id)
    return marked[0] if marked else None


def historical_verdict(conn: sqlite3.Connection, review_id: str):
    assignee = review_assignee(conn, review_id)
    if not assignee:
        return None
    rows = conn.execute(
        "SELECT author, body FROM task_comments WHERE task_id=? ORDER BY id DESC", (review_id,)
    ).fetchall()
    return next(
        (verdict for author, body in rows if author == assignee and (verdict := parse_review_verdict(body))),
        None,
    )


def historical_rejection(conn: sqlite3.Connection, review_id: str) -> bool:
    assignee = review_assignee(conn, review_id)
    if not assignee:
        return False
    return any(
        author == assignee
        and (verdict := parse_review_verdict(body)) is not None
        and verdict.decision == "changes_requested"
        for author, body in conn.execute(
            "SELECT author, body FROM task_comments WHERE task_id=? ORDER BY id DESC", (review_id,)
        )
    )


def workspace(task: sqlite3.Row) -> str:
    kind = task["workspace_kind"]
    path = task["workspace_path"]
    if kind not in {"dir", "worktree"} or not path:
        raise ValueError(f"producer {task['id']} has no persistent workspace")
    resolved = Path(path).expanduser()
    if not resolved.is_absolute() or not resolved.is_dir():
        raise ValueError(f"producer {task['id']} workspace is unavailable: {path}")
    return f"dir:{resolved}"


def workspace_head(task: sqlite3.Row) -> str:
    path = workspace(task).removeprefix("dir:")
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"producer {task['id']} workspace has no Git commit") from exc
    head = result.stdout.strip()
    if not GIT_COMMIT.fullmatch(head):
        raise ValueError(f"producer {task['id']} has no valid Git HEAD")
    return head


def remediation_producer(conn: sqlite3.Connection, review: sqlite3.Row) -> sqlite3.Row:
    """Walk through structured reviewer gates to the nearest producer."""
    current = review
    seen = {review["id"]}
    while True:
        parents = conn.execute(
            "SELECT p.* FROM task_links l JOIN tasks p ON p.id=l.parent_id WHERE l.child_id=?",
            (current["id"],),
        ).fetchall()
        if len(parents) != 1:
            raise ValueError(f"review {review['id']} must have exactly one upstream path")
        parent = parents[0]
        if parent["id"] in seen:
            raise ValueError(f"review ancestry cycle detected at {parent['id']}")
        seen.add(parent["id"])
        if historical_verdict(conn, parent["id"]):
            current = parent
            continue
        if parent["status"] != "done":
            raise ValueError(f"producer {parent['id']} is not completed")
        if not isinstance(parent["assignee"], str) or not parent["assignee"].strip():
            raise ValueError(f"producer {parent['id']} has no assignee")
        if not isinstance(review["assignee"], str) or not review["assignee"].strip():
            raise ValueError(f"review {review['id']} has no assignee")
        if parent["assignee"] == review["assignee"]:
            raise ValueError(f"producer and reviewer both use {review['assignee']}")
        return parent


def remediation_depth(conn: sqlite3.Connection, task_id: str) -> int:
    current = task_id
    seen = {current}
    depth = 0
    while True:
        parents = conn.execute(
            "SELECT p.id, p.idempotency_key FROM task_links l JOIN tasks p ON p.id=l.parent_id WHERE l.child_id=?",
            (current,),
        ).fetchall()
        remediations = [row for row in parents if (row["idempotency_key"] or "").startswith("ttf-remediation-")]
        if not remediations:
            return depth
        if len(remediations) != 1:
            raise ValueError(f"review {task_id} has ambiguous remediation ancestry")
        remediation = remediations[0]
        if remediation["id"] in seen:
            raise ValueError(f"review ancestry cycle detected at {remediation['id']}")
        seen.add(remediation["id"])
        depth += 1
        rejected = [
            row[0]
            for row in conn.execute("SELECT parent_id FROM task_links WHERE child_id=?", (remediation["id"],))
            if historical_rejection(conn, row[0])
        ]
        if len(rejected) != 1:
            raise ValueError(f"remediation {remediation['id']} has no unique rejected review parent")
        current = rejected[0]
        if current in seen:
            raise ValueError(f"review ancestry cycle detected at {current}")
        seen.add(current)


def transition_digest(producer: sqlite3.Row, review: sqlite3.Row, verdict: ReviewVerdict) -> str:
    payload = json.dumps(
        {
            "producer": producer["id"],
            "producer_assignee": producer["assignee"],
            "review": review["id"],
            "review_assignee": review["assignee"],
            "tenant": review["tenant"] or producer["tenant"],
            "workspace": workspace(producer),
            "verdict": {
                "decision": verdict.decision,
                "reviewed_commit": verdict.reviewed_commit,
                "findings": verdict.findings,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def transition_plan(conn: sqlite3.Connection, review_id: str):
    review = conn.execute("SELECT * FROM tasks WHERE id=?", (review_id,)).fetchone()
    if (
        not review
        or review["status"] != "blocked"
        or (review["block_kind"] or "") in {"needs_input", "capability"}
    ):
        return None
    if review["current_run_id"] is not None:
        raise ValueError(f"review {review_id} still has an active run")
    marked = current_verdict_marker(conn, review_id)
    if not marked or marked[0].decision != "changes_requested":
        return None
    verdict, comment_marker = marked
    producer = remediation_producer(conn, review)
    if producer["tenant"] and review["tenant"] and producer["tenant"] != review["tenant"]:
        raise ValueError(f"tenant mismatch between {producer['id']} and {review_id}")
    head = workspace_head(producer)
    if not head.lower().startswith(verdict.reviewed_commit.lower()):
        raise ValueError(
            f"reviewed commit {verdict.reviewed_commit} does not match producer {producer['id']} HEAD {head}"
        )
    digest = transition_digest(producer, review, verdict)
    depth = remediation_depth(conn, review_id)
    active = conn.execute(
        "SELECT id, idempotency_key, created_by FROM tasks WHERE status!='archived' AND ("
        "idempotency_key IN (?, ?) OR instr(COALESCE(idempotency_key, ''), ?) = 1 "
        "OR instr(COALESCE(idempotency_key, ''), ?) = 1 OR instr(COALESCE(idempotency_key, ''), ?) = 1)",
        (
            f"ttf-remediation-{review_id}",
            f"ttf-rereview-{review_id}",
            f"ttf-remediation-{review_id}-",
            f"ttf-rereview-{review_id}-",
            f"ttf-review-gate-{review_id}-",
        ),
    ).fetchall()
    if active:
        raise ValueError(f"review {review_id} already has an active or conflicting transition")
    downstream = tuple(
        row[0]
        for row in conn.execute(
            "SELECT c.id FROM task_links l JOIN tasks c ON c.id=l.child_id "
            "WHERE l.parent_id=? AND c.status!='archived' ORDER BY c.id",
            (review_id,),
        )
    )
    return review, producer, verdict, comment_marker, depth, digest, downstream


def append_event(conn: sqlite3.Connection, task_id: str, kind: str, payload: dict | None, now: int):
    conn.execute(
        "INSERT INTO task_events(task_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
        (task_id, kind, json.dumps(payload) if payload is not None else None, now),
    )


def new_task_id(conn: sqlite3.Connection) -> str:
    for _ in range(10):
        task_id = "t_" + secrets.token_hex(4)
        if not conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            return task_id
    raise RuntimeError("could not allocate a unique Hermes task id")


def inherit_notify_subs(
    conn: sqlite3.Connection, child_id: str, parents: tuple[str, ...], now: int
) -> None:
    """Mirror Hermes' native parent-to-child notification inheritance."""
    parents = tuple(dict.fromkeys(parent for parent in parents if parent))
    if not parents:
        return
    cursor = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM task_events WHERE task_id=?", (child_id,)
    ).fetchone()[0]
    placeholders = ",".join("?" * len(parents))
    conn.execute(
        f"INSERT OR IGNORE INTO kanban_notify_subs "
        "(task_id, platform, chat_id, thread_id, user_id, notifier_profile, created_at, last_event_id) "
        f"SELECT ?, platform, chat_id, thread_id, user_id, notifier_profile, ?, ? "
        f"FROM kanban_notify_subs WHERE task_id IN ({placeholders})",
        (child_id, now, cursor, *parents),
    )


def insert_task(
    conn: sqlite3.Connection,
    *,
    title: str,
    body: str,
    assignee: str | None,
    status: str,
    workspace_path: str,
    tenant: str | None,
    idempotency_key: str,
    parents: tuple[str, ...],
    block_kind: str | None = None,
    notification_parents: tuple[str, ...] = (),
) -> str:
    if conn.execute(
        "SELECT 1 FROM tasks WHERE idempotency_key=? AND status!='archived'", (idempotency_key,)
    ).fetchone():
        raise ValueError(f"active task already owns idempotency key {idempotency_key}")
    task_id = new_task_id(conn)
    now = int(time.time())
    conn.execute(
        "INSERT INTO tasks(id, title, body, assignee, status, priority, created_by, created_at, "
        "workspace_kind, workspace_path, tenant, idempotency_key, block_kind, block_recurrences) "
        "VALUES (?, ?, ?, ?, ?, 0, ?, ?, 'dir', ?, ?, ?, ?, ?)",
        (
            task_id,
            title,
            body,
            assignee,
            status,
            ENGINE_AUTHOR,
            now,
            workspace_path,
            tenant,
            idempotency_key,
            block_kind,
            1 if block_kind else 0,
        ),
    )
    for parent in parents:
        conn.execute("INSERT INTO task_links(parent_id, child_id) VALUES (?, ?)", (parent, task_id))
    append_event(
        conn,
        task_id,
        "created",
        {
            "assignee": assignee,
            "status": status,
            "parents": list(parents),
            "tenant": tenant,
            "workspace_kind": "dir",
            "workspace_path": workspace_path,
        },
        now,
    )
    inherit_notify_subs(conn, task_id, parents + notification_parents, now)
    if block_kind:
        append_event(
            conn,
            task_id,
            "blocked",
            {"reason": "owner input required", "kind": block_kind, "recurrences": 1},
            now,
        )
    return task_id


def rewire_and_archive(
    conn: sqlite3.Connection,
    review_id: str,
    successor_id: str,
    downstream: tuple[str, ...],
    digest: str,
) -> None:
    now = int(time.time())
    for child in downstream:
        conn.execute("INSERT OR IGNORE INTO task_links(parent_id, child_id) VALUES (?, ?)", (successor_id, child))
        conn.execute("DELETE FROM task_links WHERE parent_id=? AND child_id=?", (review_id, child))
        append_event(conn, child, "linked", {"parent": successor_id, "child": child}, now)
        append_event(conn, child, "unlinked", {"parent": review_id, "child": child}, now)
        inherit_notify_subs(conn, child, (successor_id,), now)
    updated = conn.execute(
        "UPDATE tasks SET status='archived', claim_lock=NULL, claim_expires=NULL, worker_pid=NULL "
        "WHERE id=? AND status='blocked' AND current_run_id IS NULL",
        (review_id,),
    )
    if updated.rowcount != 1:
        raise RuntimeError(f"review {review_id} changed during atomic transition")
    append_event(conn, review_id, "archived", {"actor": ENGINE_AUTHOR, "transition_digest": digest}, now)


def apply_transition(db_path: Path, review_id: str, owner_profile: str) -> str | None:
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        plan = transition_plan(conn, review_id)
        if not plan:
            conn.rollback()
            return None
        review, producer, verdict, _marker, depth, digest, downstream = plan
        tenant = review["tenant"] or producer["tenant"]
        workspace_path = workspace(producer).removeprefix("dir:")
        if depth >= MAX_REMEDIATION_GENERATIONS:
            gate = insert_task(
                conn,
                title=f"Owner input required for repeated review failures from {review_id}",
                body=gate_body(review_id, verdict),
                assignee=owner_profile,
                status="blocked",
                workspace_path=workspace_path,
                tenant=tenant,
                idempotency_key=f"ttf-review-gate-{review_id}-{digest}",
                parents=(producer["id"],),
                block_kind="needs_input",
                notification_parents=(review_id,),
            )
            rewire_and_archive(conn, review_id, gate, downstream, digest)
            conn.commit()
            return f"gated {review_id} -> {gate} after {depth} remediation generations"

        remediation = insert_task(
            conn,
            title=f"Remediate review findings from {review_id}",
            body=remediation_body(review_id, producer["id"], verdict),
            assignee=producer["assignee"],
            status="ready",
            workspace_path=workspace_path,
            tenant=tenant,
            idempotency_key=f"ttf-remediation-{review_id}-{digest}",
            parents=(producer["id"], review_id),
        )
        follow_up = insert_task(
            conn,
            title=f"Independent re-review of {remediation}",
            body=rereview_body(review_id, producer["id"], remediation, verdict),
            assignee=review["assignee"],
            status="todo",
            workspace_path=workspace_path,
            tenant=tenant,
            idempotency_key=f"ttf-rereview-{review_id}-{digest}",
            parents=(remediation,),
        )
        rewire_and_archive(conn, review_id, follow_up, downstream, digest)
        conn.commit()
        return f"remediated {review_id} -> {remediation} -> {follow_up}"


@contextmanager
def board_lock(db_path: Path):
    lock_path = Path(f"{db_path}.ttf-transition.lock")
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def safe_error(exc: Exception) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        return f"Git command failed with exit {exc.returncode}"
    return str(exc)


def dedupe_runtime_errors(db_path: Path, results: list[str]) -> list[str]:
    state_path = Path(f"{db_path}.ttf-transition-errors.json")
    try:
        previous = set(json.loads(state_path.read_text()).get("errors", [])) if state_path.exists() else set()
    except (OSError, AttributeError, TypeError, json.JSONDecodeError):
        previous = set()
    current = {
        hashlib.sha256(message.encode()).hexdigest()
        for message in results
        if message.startswith("error:")
    }
    visible = [
        message
        for message in results
        if not message.startswith("error:") or hashlib.sha256(message.encode()).hexdigest() not in previous
    ]
    try:
        temporary = Path(f"{state_path}.tmp")
        temporary.write_text(json.dumps({"errors": sorted(current)}), encoding="utf-8")
        os.replace(temporary, state_path)
    except OSError:
        pass
    return visible


def reconcile(board: str, home: str, dry_run: bool, owner_profile: str = "orchestrator") -> list[str]:
    board = canonical_board(board)
    db_path = check_board(home, board)
    owner_profile = owner_profile.strip().lower()
    if not BOARD_SLUG.fullmatch(owner_profile):
        raise ValueError("owner profile must be a 1-64 character Hermes slug")
    with board_lock(db_path) as acquired:
        if not acquired:
            return [LOCK_BUSY]
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            review_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM tasks WHERE status='blocked' "
                    "AND COALESCE(block_kind, '') NOT IN ('needs_input', 'capability') ORDER BY id"
                )
            ]
        messages: list[str] = []
        for review_id in review_ids:
            try:
                if dry_run:
                    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                        conn.row_factory = sqlite3.Row
                        plan = transition_plan(conn, review_id)
                    if plan:
                        action = "gate" if plan[4] >= MAX_REMEDIATION_GENERATIONS else "remediate"
                        messages.append(f"would {action} {review_id} with {len(plan[6])} downstream tasks")
                else:
                    message = apply_transition(db_path, review_id, owner_profile)
                    if message:
                        messages.append(message)
            except (OSError, TypeError, RuntimeError, ValueError, sqlite3.Error, subprocess.CalledProcessError) as exc:
                messages.append(f"error: {review_id}: {safe_error(exc)}")
        return messages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board")
    parser.add_argument("--home", default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    parser.add_argument("--owner-profile", default="orchestrator")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-board", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        verdict = parse_review_verdict(
            '{"ttf_review":{"decision":"changes_requested","reviewed_commit":"abc1234","findings":["Add a regression test"]}}'
        )
        assert verdict and "Add a regression test" in remediation_body("t_review", "t_producer", verdict)
        assert parse_review_verdict("REQUEST_CHANGES") is None
        assert parse_review_verdict('{"ttf_review":[]}') is None
        assert parse_review_verdict(
            '{"ttf_review":{"decision":"changes_requested","reviewed_commit":"abc1234","findings":[]}}'
        ) is None
        assert canonical_board("Mini-HRMS") == "mini-hrms"
        print("self-test passed")
        return 0
    if not args.board:
        parser.error("--board is required unless --self-test is used")
    try:
        if args.check_board:
            check_board(args.home, args.board)
            return 0
        results = reconcile(args.board, args.home, args.dry_run, args.owner_profile)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    if results == [LOCK_BUSY]:
        return 0
    visible = results if args.dry_run else dedupe_runtime_errors(board_db_path(args.home, args.board), results)
    for result in visible:
        print(result)
    return int(any(result.startswith("error:") for result in visible))


if __name__ == "__main__":
    raise SystemExit(main())
