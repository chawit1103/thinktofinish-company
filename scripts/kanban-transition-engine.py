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
ENGINE_KEY_PREFIXES = (
    "ttf-remediation-",
    "ttf-rereview-",
    "ttf-review-gate-",
    "ttf-refresh-review-",
)
GIT_ROUTING_ENV = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_WORK_TREE",
}


@dataclass(frozen=True)
class ReviewVerdict:
    decision: str
    reviewed_commit: str
    findings: tuple[str, ...]


@dataclass(frozen=True, order=True)
class TerminalFrontier:
    parent_id: str
    child_id: str
    path: tuple[str, ...]


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


def remediation_body(
    review_id: str,
    producer_id: str,
    verdict: ReviewVerdict,
    expected_head: str | None = None,
) -> str:
    expected_head = expected_head or verdict.reviewed_commit
    return (
        f"Remediate the independent review `{review_id}` for commit `{verdict.reviewed_commit}`.\n\n"
        f"Required findings:\n{findings_text(verdict)}\n\n"
        f"Original producer task: `{producer_id}`. Read its full task contract, acceptance criteria, requirement IDs, "
        "completion evidence, and verification commands before editing. Revalidate the complete original contract, not only "
        "the listed findings.\n\n"
        f"Before editing, verify the checkout is clean and `HEAD` is `{expected_head}`; block instead of editing if either "
        "condition changed. Work only in the declared workspace. Add deterministic regression coverage, run the task's "
        "verification commands, "
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


def peer_rereview_body(
    sibling_id: str,
    producer_id: str,
    remediation_id: str,
    verdict: ReviewVerdict,
) -> str:
    return (
        f"Read-only refresh of prior independent approval `{sibling_id}` for original producer `{producer_id}`. "
        f"That approval covered baseline `{verdict.reviewed_commit}`, which remediation task `{remediation_id}` may have "
        "invalidated.\n\n"
        "Resolve the completed remediation handoff commit from its evidence and checkout HEAD; review that new commit, not "
        "the prior approved baseline. Revalidate the prior review's complete contract and every downstream condition it "
        "gates. Return one structured ttf_review verdict whose reviewed_commit is the remediation commit; do not repair "
        "the implementation yourself."
    )


def gate_body(review_id: str, verdict: ReviewVerdict) -> str:
    return (
        f"Autonomous remediation stopped after {MAX_REMEDIATION_GENERATIONS} generations for review `{review_id}` at "
        f"commit `{verdict.reviewed_commit}`.\n\nOutstanding findings:\n{findings_text(verdict)}\n\n"
        "Owner input is required before any further remediation. This card now gates every downstream task; complete it "
        "only after recording the owner's decision and safe next action."
    )


def stale_review_body(
    review_id: str,
    producer_id: str,
    verdict: ReviewVerdict,
    current_head: str,
) -> str:
    return (
        f"Refresh independent review `{review_id}` because its verdict covered stale commit "
        f"`{verdict.reviewed_commit}` while the clean checkout is now `{current_head}`.\n\n"
        f"Prior findings to re-evaluate:\n{findings_text(verdict)}\n\n"
        f"Read the full contract and evidence for producer `{producer_id}`. Review the current checkout without editing it, "
        "rerun the required verification, and return one structured ttf_review verdict whose reviewed_commit is the current "
        "HEAD. Do not copy the stale verdict without rechecking the implementation."
    )


def stale_review_gate_body(review_id: str, verdict: ReviewVerdict) -> str:
    return (
        f"Automatic review refresh stopped after {MAX_REMEDIATION_GENERATIONS} stale generations for `{review_id}`. "
        f"The latest verdict still referenced `{verdict.reviewed_commit}`.\n\n"
        "Owner input is required to stabilize the checkout or reviewer before downstream work can continue."
    )


def terminal_replay_body(
    review_id: str,
    frontiers: tuple[tuple[str, TerminalFrontier], ...],
) -> str:
    paths = "\n".join(
        f"- approval `{approval_id}`: "
        + " -> ".join(f"`{task_id}`" for task_id in (*frontier.path, frontier.child_id))
        for approval_id, frontier in frontiers
    )
    return (
        f"Owner replay decision required after review transition `{review_id}`. Completed ordinary work below an "
        "invalidated approval may contain output from the pre-transition baseline and cannot be replayed safely by the "
        f"transition engine.\n\nAffected terminal paths and live frontiers:\n{paths}\n\n"
        "Keep this gate blocked until the completed ordinary tasks have been replayed or explicitly revalidated against "
        "the successor commit, their new evidence has been recorded, and every gated live task is safe to resume. Do not "
        "treat the prior completed output as current evidence."
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


def readonly_db_uri(db_path: Path) -> str:
    return f"{db_path.resolve().as_uri()}?mode=ro"


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
    with sqlite3.connect(readonly_db_uri(db_path), uri=True) as conn:
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


def task_ancestors(conn: sqlite3.Connection, task_id: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "WITH RECURSIVE ancestors(id) AS ("
            "SELECT parent_id FROM task_links WHERE child_id=? UNION "
            "SELECT l.parent_id FROM task_links l JOIN ancestors a ON l.child_id=a.id) "
            "SELECT id FROM ancestors",
            (task_id,),
        )
    }


def task_descendants(conn: sqlite3.Connection, task_id: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "WITH RECURSIVE descendants(id) AS ("
            "SELECT child_id FROM task_links WHERE parent_id=? UNION "
            "SELECT l.child_id FROM task_links l JOIN descendants d ON l.parent_id=d.id) "
            "SELECT id FROM descendants",
            (task_id,),
        )
    }


def terminal_descendant_frontiers(
    conn: sqlite3.Connection, task_id: str
) -> tuple[TerminalFrontier, ...]:
    frontiers: set[TerminalFrontier] = set()
    expanded: set[tuple[str, bool]] = set()
    stack: list[tuple[str, tuple[str, ...], bool]] = [(task_id, (), False)]
    while stack:
        parent_id, path, has_ordinary = stack.pop()
        state = (parent_id, has_ordinary)
        if state in expanded:
            continue
        expanded.add(state)
        children = conn.execute(
            "SELECT c.* FROM task_links l JOIN tasks c ON c.id=l.child_id "
            "WHERE l.parent_id=? ORDER BY c.id",
            (parent_id,),
        ).fetchall()
        for child in reversed(children):
            child_id = child["id"]
            if child["status"] in {"done", "archived"}:
                stack.append(
                    (
                        child_id,
                        (*path, child_id),
                        has_ordinary or historical_verdict(conn, child_id) is None,
                    )
                )
            elif path:
                frontiers.add(TerminalFrontier(parent_id, child_id, path))
    return tuple(sorted(frontiers))


def scan_approval_side_paths(
    conn: sqlite3.Connection,
    approval_id: str,
    excluded_path: set[str],
    excluded_reviews: set[str],
) -> tuple[
    tuple[str, ...],
    tuple[TerminalFrontier, ...],
]:
    direct_children: set[str] = set()
    frontiers: set[TerminalFrontier] = set()
    expanded: set[str] = set()
    stack: list[tuple[str, tuple[str, ...]]] = [(approval_id, ())]
    while stack:
        parent_id, ordinary_path = stack.pop()
        if parent_id in expanded:
            continue
        expanded.add(parent_id)
        children = conn.execute(
            "SELECT c.* FROM task_links l JOIN tasks c ON c.id=l.child_id "
            "WHERE l.parent_id=? ORDER BY c.id",
            (parent_id,),
        ).fetchall()
        for child in reversed(children):
            child_id = child["id"]
            if child_id in excluded_path or (child["idempotency_key"] or "").startswith(
                ENGINE_KEY_PREFIXES
            ):
                continue
            terminal = child["status"] in {"done", "archived"}
            if not terminal:
                if ordinary_path:
                    frontiers.add(
                        TerminalFrontier(
                            parent_id=parent_id,
                            child_id=child_id,
                            path=ordinary_path,
                        )
                    )
                else:
                    direct_children.add(child_id)
                continue
            child_verdict = historical_verdict(conn, child_id)
            if child_verdict:
                if ordinary_path and child_id not in excluded_reviews:
                    stack.append((child_id, (*ordinary_path, child_id)))
                continue
            stack.append((child_id, (*ordinary_path, child_id)))
    return (
        tuple(sorted(direct_children)),
        tuple(sorted(frontiers)),
    )


def approval_side_edges(
    conn: sqlite3.Connection,
    review: sqlite3.Row,
    producer: sqlite3.Row,
) -> tuple[
    tuple[sqlite3.Row, ReviewVerdict, tuple[str, ...], tuple[TerminalFrontier, ...]],
    ...,
]:
    ancestors = task_ancestors(conn, review["id"])
    review_descendants = task_descendants(conn, review["id"])
    if ancestors & review_descendants:
        raise ValueError(f"review ancestry cycle detected at {review['id']}")
    excluded_reviews = {review["id"]}
    candidates: dict[str, tuple[sqlite3.Row, ReviewVerdict]] = {}
    for ancestor_id in sorted(ancestors):
        if ancestor_id == producer["id"] or ancestor_id in excluded_reviews:
            continue
        ancestor = conn.execute("SELECT * FROM tasks WHERE id=?", (ancestor_id,)).fetchone()
        if not ancestor or ancestor["status"] not in {"done", "archived"}:
            continue
        if verdict := historical_verdict(conn, ancestor_id):
            candidates[ancestor_id] = (ancestor, verdict)
    frontier = [producer["id"], *sorted(ancestors)]
    expanded: set[str] = set()
    while frontier:
        parent_id = frontier.pop()
        if parent_id in expanded:
            continue
        expanded.add(parent_id)
        children = conn.execute(
            "SELECT c.* FROM task_links l JOIN tasks c ON c.id=l.child_id "
            "WHERE l.parent_id=? ORDER BY c.id",
            (parent_id,),
        ).fetchall()
        for child in children:
            if child["id"] in excluded_reviews or child["status"] not in {"done", "archived"}:
                continue
            child_verdict = historical_verdict(conn, child["id"])
            if not child_verdict:
                continue
            candidates[child["id"]] = (child, child_verdict)
            frontier.append(child["id"])
    scans: dict[str, tuple[tuple[str, ...], tuple[TerminalFrontier, ...]]] = {}
    for candidate_id in sorted(candidates):
        direct_children, terminal_frontiers = scan_approval_side_paths(
            conn,
            candidate_id,
            ancestors | {review["id"]},
            excluded_reviews,
        )
        scans[candidate_id] = (direct_children, terminal_frontiers)
    approvals = []
    for sibling, verdict in (candidates[task_id] for task_id in sorted(candidates)):
        side_children, terminal_frontiers = scans[sibling["id"]]
        if verdict.decision != "approved":
            if sibling["status"] == "archived" and not side_children and not terminal_frontiers:
                continue
            raise ValueError(
                f"terminal sibling review {sibling['id']} gating live work has a non-approved verdict"
            )
        if not side_children and not terminal_frontiers:
            continue
        if not isinstance(sibling["assignee"], str) or not sibling["assignee"].strip():
            raise ValueError(f"terminal sibling review {sibling['id']} has no assignee")
        if sibling["tenant"] and (review["tenant"] or producer["tenant"]):
            if sibling["tenant"] != (review["tenant"] or producer["tenant"]):
                raise ValueError(f"tenant mismatch between {sibling['id']} and {review['id']}")
        approvals.append((sibling, verdict, side_children, terminal_frontiers))
    return tuple(approvals)


def git_output(task_id: str, path: Path, *args: str, input_text: str | None = None) -> str:
    env = os.environ.copy()
    for key in GIT_ROUTING_ENV:
        env.pop(key, None)
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            check=True,
            encoding="utf-8",
            errors="surrogateescape",
            capture_output=True,
            timeout=15,
            env=env,
            input=input_text,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"producer {task_id} workspace is not a usable Git checkout") from exc
    return result.stdout


def checkout_root(task_id: str, path: str) -> Path:
    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        raise ValueError(f"producer {task_id} workspace is unavailable: {path}")
    resolved = expanded.resolve()
    if not resolved.is_dir():
        raise ValueError(f"producer {task_id} workspace is unavailable: {path}")
    root = Path(git_output(task_id, resolved, "rev-parse", "--show-toplevel").strip()).resolve()
    return root


def workspace(task: sqlite3.Row) -> str:
    kind = task["workspace_kind"]
    path = task["workspace_path"]
    if kind not in {"dir", "worktree"} or not path:
        raise ValueError(f"producer {task['id']} has no persistent workspace")
    declared = Path(path).expanduser()
    root = checkout_root(task["id"], path)
    if root != declared.resolve():
        raise ValueError(f"producer {task['id']} workspace must be the Git checkout root: {root}")
    return f"dir:{root}"


def require_clean_checkout(task_id: str, path: Path, seen: set[Path] | None = None) -> None:
    seen = seen or set()
    path = path.resolve()
    if path in seen:
        raise ValueError(f"producer {task_id} workspace has a recursive submodule")
    seen.add(path)
    flags = git_output(task_id, path, "ls-files", "-v", "-z")
    if any(entry[:1] == "S" or entry[:1].islower() for entry in flags.split("\0") if entry):
        raise ValueError(f"producer {task_id} workspace uses hidden Git index flags")
    status = git_output(
        task_id, path, "status", "--porcelain=v1", "--untracked-files=normal", "--ignore-submodules=none"
    )
    if status:
        raise ValueError(f"producer {task_id} workspace is dirty; commit or clean every tracked/untracked change")
    for entry in git_output(task_id, path, "ls-files", "--stage", "-z").split("\0"):
        metadata, separator, relative = entry.partition("\t")
        if not separator or not metadata.startswith("160000 "):
            continue
        submodule = (path / relative).resolve()
        if not submodule.is_relative_to(path):
            raise ValueError(f"producer {task_id} workspace has an unsafe submodule path")
        if (submodule / ".git").exists():
            require_clean_checkout(task_id, submodule, seen)


def workspace_head(task: sqlite3.Row) -> str:
    path = Path(workspace(task).removeprefix("dir:"))
    require_clean_checkout(task["id"], path)
    head = git_output(task["id"], path, "rev-parse", "HEAD").strip()
    require_clean_checkout(task["id"], path)
    confirmed_head = git_output(task["id"], path, "rev-parse", "HEAD").strip()
    if head != confirmed_head:
        raise ValueError(f"producer {task['id']} workspace changed during verification")
    if not GIT_COMMIT.fullmatch(confirmed_head):
        raise ValueError(f"producer {task['id']} has no valid Git HEAD")
    return confirmed_head


def resolve_reviewed_commit(task_id: str, path: Path, commit: str) -> str | None:
    try:
        objects = [
            value
            for value in git_output(task_id, path, "rev-parse", f"--disambiguate={commit.lower()}").splitlines()
            if GIT_COMMIT.fullmatch(value)
        ]
        if len(objects) != 1:
            return None
        resolved = objects[0]
        object_type = git_output(
            task_id,
            path,
            "cat-file",
            "--batch-check=%(objecttype)",
            input_text=f"{resolved}\n",
        ).strip()
    except ValueError:
        return None
    return resolved if object_type == "commit" else None


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


def transition_depths(conn: sqlite3.Connection, task_id: str) -> tuple[int, int]:
    current = conn.execute("SELECT id, idempotency_key FROM tasks WHERE id=?", (task_id,)).fetchone()
    seen: set[str] = set()
    remediation_depth = 0
    refresh_depth = 0
    while True:
        if not current:
            return remediation_depth, refresh_depth
        if current["id"] in seen:
            raise ValueError(f"review ancestry cycle detected at {current['id']}")
        seen.add(current["id"])
        key = current["idempotency_key"] or ""
        remediation_depth += key.startswith("ttf-remediation-")
        refresh_depth += key.startswith("ttf-refresh-review-")
        parents = conn.execute(
            "SELECT p.id, p.idempotency_key FROM task_links l JOIN tasks p ON p.id=l.parent_id WHERE l.child_id=?",
            (current["id"],),
        ).fetchall()
        if key.startswith("ttf-remediation-"):
            lineage = [row for row in parents if historical_rejection(conn, row["id"])]
            if len(lineage) != 1:
                raise ValueError(f"remediation {current['id']} has no unique rejected review parent")
        else:
            lineage = [
                row for row in parents if (row["idempotency_key"] or "").startswith("ttf-remediation-")
            ]
            if not lineage:
                lineage = [row for row in parents if historical_verdict(conn, row["id"])]
            if len(lineage) > 1:
                raise ValueError(f"review {task_id} has ambiguous transition ancestry")
            if not lineage:
                return remediation_depth, refresh_depth
        current = lineage[0]


def remediation_depth(conn: sqlite3.Connection, task_id: str) -> int:
    return transition_depths(conn, task_id)[0]


def stale_refresh_depth(conn: sqlite3.Connection, task_id: str) -> int:
    return transition_depths(conn, task_id)[1]


def transition_digest(
    producer: sqlite3.Row,
    review: sqlite3.Row,
    verdict: ReviewVerdict,
    workspace_head: str,
) -> str:
    payload = json.dumps(
        {
            "producer": producer["id"],
            "producer_assignee": producer["assignee"],
            "review": review["id"],
            "review_assignee": review["assignee"],
            "tenant": review["tenant"] or producer["tenant"],
            "workspace": workspace(producer),
            "workspace_head": workspace_head,
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


def candidate_shares_checkout(
    candidate: sqlite3.Row, producer_root: Path, *, fail_closed: bool = True
) -> bool:
    raw_path = candidate["workspace_path"]
    if not isinstance(raw_path, str) or not raw_path or not Path(raw_path).expanduser().is_absolute():
        if fail_closed:
            raise ValueError(f"active transition {candidate['id']} has an unverifiable workspace")
        return False
    try:
        candidate_path = Path(raw_path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        if fail_closed:
            raise ValueError(f"active transition {candidate['id']} has an unverifiable workspace") from exc
        return False
    if (
        candidate_path == producer_root
        or candidate_path.is_relative_to(producer_root)
        or producer_root.is_relative_to(candidate_path)
    ):
        return True
    try:
        return checkout_root(candidate["id"], raw_path) == producer_root
    except ValueError as exc:
        if fail_closed:
            raise ValueError(f"active transition {candidate['id']} has an unverifiable workspace") from exc
        return False


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
    active = conn.execute(
        "SELECT id, idempotency_key, created_by FROM tasks WHERE status!='archived' AND ("
        "idempotency_key IN (?, ?) OR instr(COALESCE(idempotency_key, ''), ?) = 1 "
        "OR instr(COALESCE(idempotency_key, ''), ?) = 1 OR instr(COALESCE(idempotency_key, ''), ?) = 1 "
        "OR instr(COALESCE(idempotency_key, ''), ?) = 1)",
        (
            f"ttf-remediation-{review_id}",
            f"ttf-rereview-{review_id}",
            f"ttf-remediation-{review_id}-",
            f"ttf-rereview-{review_id}-",
            f"ttf-review-gate-{review_id}-",
            f"ttf-refresh-review-{review_id}-",
        ),
    ).fetchall()
    if active:
        raise ValueError(f"review {review_id} already has an active or conflicting transition")
    approval_edges = approval_side_edges(conn, review, producer)
    descendant_frontiers = terminal_descendant_frontiers(conn, review_id)
    downstream_rows = conn.execute(
        "SELECT c.id, c.status FROM task_links l JOIN tasks c ON c.id=l.child_id "
        "WHERE l.parent_id=? AND c.status!='archived' ORDER BY c.id",
        (review_id,),
    ).fetchall()
    downstream = tuple(row["id"] for row in downstream_rows)
    regated_children = {
        child_id
        for _sibling, _verdict, children, terminal_frontiers in approval_edges
        for child_id in (
            *children,
            *(frontier.child_id for frontier in terminal_frontiers),
        )
    } | {frontier.child_id for frontier in descendant_frontiers} | set(downstream)
    producer_workspace = workspace(producer).removeprefix("dir:")
    candidates = conn.execute(
        "WITH candidates AS (SELECT t.*, EXISTS ("
        "SELECT 1 FROM task_links l WHERE l.parent_id=? AND l.child_id=t.id) AS same_producer, "
        "(instr(COALESCE(t.idempotency_key, ''), 'ttf-remediation-')=1 "
        "OR instr(COALESCE(t.idempotency_key, ''), 'ttf-rereview-')=1 "
        "OR instr(COALESCE(t.idempotency_key, ''), 'ttf-review-gate-')=1 "
        "OR instr(COALESCE(t.idempotency_key, ''), 'ttf-refresh-review-')=1) AS engine_transition, "
        "NOT EXISTS (SELECT 1 FROM task_links pl JOIN tasks p ON p.id=pl.parent_id "
        "WHERE pl.child_id=t.id AND p.status NOT IN ('done', 'archived')) AS parents_terminal "
        "FROM tasks t WHERE t.id!=?) "
        "SELECT id, status, current_run_id, claim_lock, worker_pid, workspace_kind, workspace_path, "
        "same_producer, engine_transition FROM candidates WHERE "
        "(current_run_id IS NOT NULL OR claim_lock IS NOT NULL OR worker_pid IS NOT NULL "
        "OR status IN ('running', 'review') "
        "OR (status IN ('todo', 'ready') AND parents_terminal))",
        (producer["id"], review_id),
    ).fetchall()
    producer_root = Path(producer_workspace)
    tentatively_skipped_children: set[str] = set()
    for candidate in candidates:
        if candidate["id"] in regated_children:
            if (
                candidate["status"] in {"todo", "ready"}
                and candidate["current_run_id"] is None
                and candidate["claim_lock"] is None
                and candidate["worker_pid"] is None
            ):
                tentatively_skipped_children.add(candidate["id"])
                continue
            return None
        if candidate["same_producer"]:
            return None
        if candidate["engine_transition"] or candidate["workspace_kind"] in {"dir", "worktree"}:
            if candidate_shares_checkout(
                candidate, producer_root, fail_closed=bool(candidate["engine_transition"])
            ):
                return None
    head = workspace_head(producer)
    reviewed_head = resolve_reviewed_commit(producer["id"], producer_root, verdict.reviewed_commit)
    digest = transition_digest(producer, review, verdict, head)
    depth, refresh_depth = transition_depths(conn, review_id)
    peer_approvals = tuple(
        (
            sibling,
            sibling_verdict,
            side_children,
            terminal_frontiers,
            resolve_reviewed_commit(
                producer["id"], producer_root, sibling_verdict.reviewed_commit
            ),
        )
        for sibling, sibling_verdict, side_children, terminal_frontiers in approval_edges
    )
    actual_approvals = (
        tuple(approval for approval in peer_approvals if approval[4] != head)
        if reviewed_head != head or depth >= MAX_REMEDIATION_GENERATIONS
        else peer_approvals
    )
    actual_regated_children = {
        child_id
        for _sibling, _verdict, children, terminal_frontiers, _reviewed_head in actual_approvals
        for child_id in (
            *children,
            *(frontier.child_id for frontier in terminal_frontiers),
        )
    } | {frontier.child_id for frontier in descendant_frontiers} | set(downstream)
    if tentatively_skipped_children - actual_regated_children:
        return None
    return (
        review,
        producer,
        verdict,
        comment_marker,
        depth,
        digest,
        downstream,
        head,
        refresh_depth,
        reviewed_head,
        peer_approvals,
        descendant_frontiers,
    )


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


def rewire_children(
    conn: sqlite3.Connection,
    source_id: str,
    successor_id: str,
    downstream: tuple[str, ...],
) -> None:
    now = int(time.time())
    for child in downstream:
        conn.execute("INSERT OR IGNORE INTO task_links(parent_id, child_id) VALUES (?, ?)", (successor_id, child))
        conn.execute(
            "UPDATE tasks SET status='todo' WHERE id=? AND status='ready' AND current_run_id IS NULL",
            (child,),
        )
        conn.execute("DELETE FROM task_links WHERE parent_id=? AND child_id=?", (source_id, child))
        append_event(conn, child, "linked", {"parent": successor_id, "child": child}, now)
        append_event(conn, child, "unlinked", {"parent": source_id, "child": child}, now)
        inherit_notify_subs(conn, child, (successor_id,), now)


def terminal_frontiers_for(approvals) -> tuple[tuple[str, TerminalFrontier], ...]:
    return tuple(
        sorted(
            (sibling["id"], frontier)
            for sibling, _verdict, _children, frontiers, _reviewed_head in approvals
            for frontier in frontiers
        )
    )


def merge_terminal_frontiers(*groups) -> tuple[tuple[str, TerminalFrontier], ...]:
    merged: dict[tuple[str, str, str], tuple[str, TerminalFrontier]] = {}
    for group in groups:
        for approval_id, frontier in group:
            merged[(approval_id, frontier.parent_id, frontier.child_id)] = (approval_id, frontier)
    return tuple(sorted(merged.values()))


def terminal_gate_parents(
    conn: sqlite3.Connection,
    review_id: str,
    frontiers: tuple[tuple[str, TerminalFrontier], ...],
) -> tuple[str, ...]:
    review_descendants = task_descendants(conn, review_id)
    return tuple(
        sorted(
            {
                frontier.parent_id
                for _approval_id, frontier in frontiers
                if frontier.parent_id not in review_descendants
            }
        )
    )


def gate_terminal_frontiers(
    conn: sqlite3.Connection,
    gate_id: str,
    frontiers: tuple[tuple[str, TerminalFrontier], ...],
) -> None:
    now = int(time.time())
    for child_id in sorted({frontier.child_id for _approval_id, frontier in frontiers}):
        child = conn.execute(
            "SELECT status, current_run_id, claim_lock, worker_pid FROM tasks WHERE id=?",
            (child_id,),
        ).fetchone()
        if not child or child["status"] in {"done", "archived"}:
            raise RuntimeError(f"terminal side-path frontier {child_id} changed during atomic transition")
        if (
            child["current_run_id"] is not None
            or child["claim_lock"] is not None
            or child["worker_pid"] is not None
            or child["status"] in {"running", "review"}
        ):
            raise RuntimeError(f"terminal side-path frontier {child_id} became active")
        inserted = conn.execute(
            "INSERT OR IGNORE INTO task_links(parent_id, child_id) VALUES (?, ?)",
            (gate_id, child_id),
        )
        conn.execute(
            "UPDATE tasks SET status='todo' WHERE id=? AND status='ready' "
            "AND current_run_id IS NULL AND claim_lock IS NULL AND worker_pid IS NULL",
            (child_id,),
        )
        if inserted.rowcount:
            append_event(conn, child_id, "linked", {"parent": gate_id, "child": child_id}, now)
            inherit_notify_subs(conn, child_id, (gate_id,), now)


def rewire_and_archive(
    conn: sqlite3.Connection,
    review_id: str,
    successor_id: str,
    downstream: tuple[str, ...],
    digest: str,
) -> None:
    rewire_children(conn, review_id, successor_id, downstream)
    now = int(time.time())
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
        (
            review,
            producer,
            verdict,
            _marker,
            depth,
            digest,
            downstream,
            head,
            refresh_depth,
            reviewed_head,
            peer_approvals,
            descendant_frontiers,
        ) = plan
        tenant = review["tenant"] or producer["tenant"]
        workspace_path = workspace(producer).removeprefix("dir:")
        stale_peer_approvals = tuple(
            approval for approval in peer_approvals if approval[4] != head
        )
        classified_descendants: dict[tuple[str, str], tuple[bool, TerminalFrontier]] = {}
        for frontier in descendant_frontiers:
            review_only = all(historical_verdict(conn, task_id) for task_id in frontier.path)
            key = (frontier.parent_id, frontier.child_id)
            if key not in classified_descendants or not review_only:
                classified_descendants[key] = (review_only, frontier)
        descendant_review_frontiers = [
            (review_id, frontier)
            for review_only, frontier in classified_descendants.values()
            if review_only
        ]
        descendant_replay_frontiers = [
            (review_id, frontier)
            for review_only, frontier in classified_descendants.values()
            if not review_only
        ]
        if reviewed_head != head:
            if refresh_depth >= MAX_REMEDIATION_GENERATIONS:
                replay_frontiers = merge_terminal_frontiers(
                    descendant_replay_frontiers,
                    terminal_frontiers_for(stale_peer_approvals),
                )
                replay_parents = terminal_gate_parents(conn, review_id, replay_frontiers)
                body = stale_review_gate_body(review_id, verdict)
                if replay_frontiers:
                    body += "\n\n" + terminal_replay_body(review_id, replay_frontiers)
                gate = insert_task(
                    conn,
                    title=f"Owner input required for repeated stale reviews from {review_id}",
                    body=body,
                    assignee=owner_profile,
                    status="blocked",
                    workspace_path=workspace_path,
                    tenant=tenant,
                    idempotency_key=f"ttf-review-gate-{review_id}-{digest}",
                    parents=(producer["id"], *replay_parents),
                    block_kind="needs_input",
                    notification_parents=(
                        review_id,
                        *(approval[0]["id"] for approval in stale_peer_approvals),
                        *(frontier.child_id for _approval_id, frontier in replay_frontiers),
                    ),
                )
                for (
                    sibling,
                    _sibling_verdict,
                    side_children,
                    _terminal_frontiers,
                    _sibling_head,
                ) in stale_peer_approvals:
                    rewire_children(conn, sibling["id"], gate, side_children)
                gate_terminal_frontiers(conn, gate, replay_frontiers)
                gate_terminal_frontiers(conn, gate, descendant_review_frontiers)
                rewire_and_archive(conn, review_id, gate, downstream, digest)
                conn.commit()
                return f"gated stale review {review_id} -> {gate} after {refresh_depth} refreshes"
            refresh = insert_task(
                conn,
                title=f"Refresh stale independent review from {review_id}",
                body=stale_review_body(review_id, producer["id"], verdict, head),
                assignee=review["assignee"],
                status="ready",
                workspace_path=workspace_path,
                tenant=tenant,
                idempotency_key=f"ttf-refresh-review-{review_id}-{digest}",
                parents=(review_id,),
            )
            peer_refreshes: dict[str, str] = {}
            for (
                sibling,
                sibling_verdict,
                side_children,
                _terminal_frontiers,
                _sibling_head,
            ) in stale_peer_approvals:
                peer_refresh = insert_task(
                    conn,
                    title=f"Refresh stale prior approval from {sibling['id']}",
                    body=stale_review_body(
                        sibling["id"], producer["id"], sibling_verdict, head
                    ),
                    assignee=sibling["assignee"],
                    status="ready",
                    workspace_path=workspace_path,
                    tenant=tenant,
                    idempotency_key=(
                        f"ttf-refresh-review-{review_id}-peer-{sibling['id']}-{digest}"
                    ),
                    parents=(review_id,),
                    notification_parents=(sibling["id"],),
                )
                peer_refreshes[sibling["id"]] = peer_refresh
                rewire_children(conn, sibling["id"], peer_refresh, side_children)
            gate_terminal_frontiers(conn, refresh, descendant_review_frontiers)
            replay_frontiers = merge_terminal_frontiers(
                descendant_replay_frontiers,
                terminal_frontiers_for(stale_peer_approvals),
            )
            if replay_frontiers:
                affected_approvals = {approval_id for approval_id, _frontier in replay_frontiers}
                replay_gate = insert_task(
                    conn,
                    title=f"Owner replay required for stale side paths from {review_id}",
                    body=terminal_replay_body(review_id, replay_frontiers),
                    assignee=owner_profile,
                    status="blocked",
                    workspace_path=workspace_path,
                    tenant=tenant,
                    idempotency_key=f"ttf-review-gate-{review_id}-replay-{digest}",
                    parents=(
                        refresh,
                        *(
                            peer_refreshes[approval_id]
                            for approval_id in sorted(affected_approvals)
                            if approval_id in peer_refreshes
                        ),
                        *sorted({frontier.parent_id for _approval_id, frontier in replay_frontiers}),
                    ),
                    block_kind="needs_input",
                    notification_parents=(
                        review_id,
                        *sorted(affected_approvals),
                        *(frontier.child_id for _approval_id, frontier in replay_frontiers),
                    ),
                )
                gate_terminal_frontiers(conn, replay_gate, replay_frontiers)
            rewire_and_archive(conn, review_id, refresh, downstream, digest)
            conn.commit()
            return f"refreshed stale review {review_id} -> {refresh} at {head}"
        if depth >= MAX_REMEDIATION_GENERATIONS:
            replay_frontiers = merge_terminal_frontiers(
                descendant_replay_frontiers,
                terminal_frontiers_for(stale_peer_approvals),
            )
            replay_parents = terminal_gate_parents(conn, review_id, replay_frontiers)
            body = gate_body(review_id, verdict)
            if replay_frontiers:
                body += "\n\n" + terminal_replay_body(review_id, replay_frontiers)
            gate = insert_task(
                conn,
                title=f"Owner input required for repeated review failures from {review_id}",
                body=body,
                assignee=owner_profile,
                status="blocked",
                workspace_path=workspace_path,
                tenant=tenant,
                idempotency_key=f"ttf-review-gate-{review_id}-{digest}",
                parents=(producer["id"], *replay_parents),
                block_kind="needs_input",
                notification_parents=(
                    review_id,
                    *(approval[0]["id"] for approval in stale_peer_approvals),
                    *(frontier.child_id for _approval_id, frontier in replay_frontiers),
                ),
            )
            for (
                sibling,
                _sibling_verdict,
                side_children,
                _terminal_frontiers,
                _sibling_head,
            ) in stale_peer_approvals:
                rewire_children(conn, sibling["id"], gate, side_children)
            gate_terminal_frontiers(conn, gate, replay_frontiers)
            gate_terminal_frontiers(conn, gate, descendant_review_frontiers)
            rewire_and_archive(conn, review_id, gate, downstream, digest)
            conn.commit()
            return f"gated {review_id} -> {gate} after {depth} remediation generations"

        remediation = insert_task(
            conn,
            title=f"Remediate review findings from {review_id}",
            body=remediation_body(review_id, producer["id"], verdict, head),
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
        peer_reviews: dict[str, str] = {}
        for (
            sibling,
            sibling_verdict,
            side_children,
            _terminal_frontiers,
            _sibling_head,
        ) in peer_approvals:
            peer_review = insert_task(
                conn,
                title=f"Refresh prior approval from {sibling['id']} after {remediation}",
                body=peer_rereview_body(
                    sibling["id"], producer["id"], remediation, sibling_verdict
                ),
                assignee=sibling["assignee"],
                status="todo",
                workspace_path=workspace_path,
                tenant=tenant,
                idempotency_key=(
                    f"ttf-rereview-{review_id}-peer-{sibling['id']}-{digest}"
                ),
                parents=(remediation,),
                notification_parents=(sibling["id"],),
            )
            peer_reviews[sibling["id"]] = peer_review
            rewire_children(conn, sibling["id"], peer_review, side_children)
        gate_terminal_frontiers(conn, follow_up, descendant_review_frontiers)
        replay_frontiers = merge_terminal_frontiers(
            descendant_replay_frontiers,
            terminal_frontiers_for(peer_approvals),
        )
        if replay_frontiers:
            affected_approvals = {approval_id for approval_id, _frontier in replay_frontiers}
            replay_gate = insert_task(
                conn,
                title=f"Owner replay required for completed side paths from {review_id}",
                body=terminal_replay_body(review_id, replay_frontiers),
                assignee=owner_profile,
                status="blocked",
                workspace_path=workspace_path,
                tenant=tenant,
                idempotency_key=f"ttf-review-gate-{review_id}-replay-{digest}",
                parents=(
                    follow_up,
                    *(
                        peer_reviews[approval_id]
                        for approval_id in sorted(affected_approvals)
                        if approval_id in peer_reviews
                    ),
                    *sorted({frontier.parent_id for _approval_id, frontier in replay_frontiers}),
                ),
                block_kind="needs_input",
                notification_parents=(
                    review_id,
                    *sorted(affected_approvals),
                    *(frontier.child_id for _approval_id, frontier in replay_frontiers),
                ),
            )
            gate_terminal_frontiers(conn, replay_gate, replay_frontiers)
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
        with sqlite3.connect(readonly_db_uri(db_path), uri=True) as conn:
            review_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM tasks WHERE status='blocked' "
                    "AND COALESCE(block_kind, '') NOT IN ('needs_input', 'capability') ORDER BY id"
                )
            ]
        messages: list[str] = []
        reserved_lanes: set[str] = set()
        for review_id in review_ids:
            try:
                if dry_run:
                    with sqlite3.connect(readonly_db_uri(db_path), uri=True) as conn:
                        conn.row_factory = sqlite3.Row
                        plan = transition_plan(conn, review_id)
                    if plan:
                        lane = workspace(plan[1])
                        if lane in reserved_lanes:
                            messages.append(f"would defer {review_id} because workspace lane is busy")
                            continue
                        reserved_lanes.add(lane)
                        stale = plan[9] != plan[7]
                        if stale:
                            action = "gate stale review" if plan[8] >= MAX_REMEDIATION_GENERATIONS else "refresh"
                        else:
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
    return int(any(result.startswith("error:") for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
