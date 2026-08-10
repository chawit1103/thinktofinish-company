import os
import runpy
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
ENGINE = runpy.run_path(str(ROOT / "scripts" / "kanban-transition-engine.py"))
REAL_WORKSPACE_HEAD = ENGINE["workspace_head"]
REAL_RESOLVE_REVIEWED_COMMIT = ENGINE["resolve_reviewed_commit"]
VERDICT = '{"ttf_review":{"decision":"changes_requested","reviewed_commit":"abc1234","findings":["Add a regression test"]}}'
APPROVED = '{"ttf_review":{"decision":"approved","reviewed_commit":"abc1234","findings":[]}}'


@pytest.fixture(autouse=True)
def stable_test_head(monkeypatch):
    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", lambda task: "abc1234")
    monkeypatch.setitem(
        ENGINE["transition_plan"].__globals__,
        "resolve_reviewed_commit",
        lambda task_id, path, commit: commit,
    )


def make_board(tmp_path, board="demo"):
    home = tmp_path / "hermes"
    workspace = home / "worktree"
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", str(workspace)], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(workspace), "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-m", "initial",
        ],
        check=True,
        capture_output=True,
    )
    db_path = home / "kanban" / "boards" / board / "kanban.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY, title TEXT, body TEXT, status TEXT, assignee TEXT,
                priority INTEGER DEFAULT 0, created_by TEXT, created_at INTEGER NOT NULL DEFAULT 0,
                workspace_kind TEXT, workspace_path TEXT, tenant TEXT, idempotency_key TEXT,
                block_kind TEXT, block_recurrences INTEGER NOT NULL DEFAULT 0,
                claim_lock TEXT, claim_expires INTEGER, worker_pid INTEGER,
                current_run_id INTEGER
            );
            CREATE TABLE task_links (parent_id TEXT, child_id TEXT);
            CREATE TABLE task_comments (
                id INTEGER PRIMARY KEY, task_id TEXT, author TEXT NOT NULL, body TEXT
            );
            CREATE TABLE task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, kind TEXT, payload TEXT, created_at INTEGER
            );
            CREATE TABLE kanban_notify_subs (
                task_id TEXT NOT NULL, platform TEXT NOT NULL, chat_id TEXT NOT NULL,
                thread_id TEXT NOT NULL DEFAULT '', user_id TEXT, notifier_profile TEXT,
                created_at INTEGER NOT NULL, last_event_id INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (task_id, platform, chat_id, thread_id)
            );
            """
        )
    return home, db_path, workspace


def add_tasks(db_path, tasks, links=(), comments=()):
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO tasks(id, status, assignee, workspace_kind, workspace_path, tenant, "
            "idempotency_key, block_kind, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tasks,
        )
        conn.executemany("INSERT INTO task_links VALUES (?, ?)", links)
        for task, body in comments:
            row = conn.execute("SELECT assignee FROM tasks WHERE id=?", (task,)).fetchone()
            conn.execute(
                "INSERT INTO task_comments(task_id, author, body) VALUES (?, ?, ?)",
                (task, row[0] if row and row[0] else "unknown", body),
            )


def transition_rows(conn, review_id):
    remediation = conn.execute(
        "SELECT * FROM tasks WHERE idempotency_key LIKE ?", (f"ttf-remediation-{review_id}-%",)
    ).fetchone()
    rereview = conn.execute(
        "SELECT * FROM tasks WHERE idempotency_key LIKE ?", (f"ttf-rereview-{review_id}-%",)
    ).fetchone()
    return remediation, rereview


def test_mixed_reviewer_chain_is_rewired_atomically_with_full_context(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), "tenant-a", None, None, "full contract"),
            ("t_irev", "done", "code-reviewer", "worktree", str(workspace), "tenant-a", None, None, None),
            ("t_qa", "blocked", "safety-reviewer", "worktree", str(workspace), "tenant-a", None, None, None),
            ("t_next", "todo", "release-manager", "worktree", str(workspace), "tenant-a", None, None, None),
        ],
        [("t_prod", "t_irev"), ("t_irev", "t_qa"), ("t_qa", "t_next")],
        [("t_irev", APPROVED), ("t_qa", VERDICT)],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO task_comments(task_id, author, body) VALUES "
            "('t_irev', 'code-reviewer', 'later audit note')"
        )
        conn.execute(
            "INSERT INTO kanban_notify_subs "
            "(task_id, platform, chat_id, thread_id, user_id, notifier_profile, created_at) "
            "VALUES ('t_qa', 'telegram', 'chat-1', '', 'owner-1', 'orchestrator', 1)"
        )

    result = ENGINE["reconcile"]("demo", str(home), False)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        remediation, rereview = transition_rows(conn, "t_qa")
        links = {tuple(row) for row in conn.execute("SELECT parent_id, child_id FROM task_links")}
        assert result == [f"remediated t_qa -> {remediation['id']} -> {rereview['id']}"]
        assert conn.execute("SELECT status FROM tasks WHERE id='t_qa'").fetchone()[0] == "archived"
        assert remediation["status"] == "ready" and remediation["assignee"] == "engineer"
        assert remediation["tenant"] == "tenant-a" and remediation["workspace_kind"] == "dir"
        assert remediation["workspace_path"] == str(workspace)
        assert remediation["created_by"] == rereview["created_by"] == "ttf-transition-engine"
        assert "Original producer task: `t_prod`" in remediation["body"]
        assert "verify the checkout is clean and `HEAD` is `abc1234`" in remediation["body"]
        assert rereview["status"] == "todo" and rereview["assignee"] == "safety-reviewer"
        assert {("t_prod", remediation["id"]), ("t_qa", remediation["id"])} <= links
        assert (remediation["id"], rereview["id"]) in links
        assert (rereview["id"], "t_next") in links and ("t_qa", "t_next") not in links
        assert conn.execute("SELECT COUNT(*) FROM task_events WHERE kind='archived'").fetchone()[0] == 1
        notified = {
            row[0]
            for row in conn.execute(
                "SELECT task_id FROM kanban_notify_subs WHERE platform='telegram' AND chat_id='chat-1'"
            )
        }
        assert {"t_qa", remediation["id"], rereview["id"], "t_next"} <= notified


def test_review_payload_parser_is_strict():
    assert ENGINE["parse_review_verdict"]('{"ttf_review":[]}') is None
    assert ENGINE["parse_review_verdict"](
        '{"ttf_review":{"decision":"changes_requested","reviewed_commit":"not-a-sha","findings":["fix"]}}'
    ) is None


def test_verdict_must_be_current_or_immediately_precede_block_comment(tmp_path):
    _, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None)],
        comments=[("t_review", VERDICT)],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO task_comments(task_id, author, body) VALUES ('t_review', 'qa', 'BLOCKED: changes requested')"
        )
        assert ENGINE["latest_verdict"](conn, "t_review").decision == "changes_requested"
        conn.execute(
            "INSERT INTO task_comments(task_id, author, body) VALUES ('t_review', 'qa', 'newer operator note')"
        )
        assert ENGINE["latest_verdict"](conn, "t_review") is None


def test_verdict_author_must_match_reviewer(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review")],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO task_comments(task_id, author, body) VALUES ('t_review', 'engineer', ?)",
            (VERDICT,),
        )
    assert ENGINE["reconcile"]("demo", str(home), False) == []


def test_stale_review_is_planned_for_refresh(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    stale = VERDICT.replace("abc1234", "def5678")
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review")],
        [("t_review", stale)],
    )
    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", lambda task: "abc1234")
    assert ENGINE["reconcile"]("demo", str(home), True) == ["would refresh t_review with 0 downstream tasks"]


def test_stale_review_creates_runnable_refresh_for_real_head(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    reviewed_head = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    verdict = VERDICT.replace("abc1234", reviewed_head)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review")],
        [("t_review", verdict)],
    )
    subprocess.run(
        [
            "git", "-C", str(workspace), "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-m", "other remediation",
        ],
        check=True,
        capture_output=True,
    )
    current_head = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", REAL_WORKSPACE_HEAD)
    monkeypatch.setitem(
        ENGINE["transition_plan"].__globals__, "resolve_reviewed_commit", REAL_RESOLVE_REVIEWED_COMMIT
    )

    result = ENGINE["reconcile"]("demo", str(home), False)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        refresh = conn.execute(
            "SELECT * FROM tasks WHERE idempotency_key LIKE 'ttf-refresh-review-t_review-%'"
        ).fetchone()
        assert result == [f"refreshed stale review t_review -> {refresh['id']} at {current_head}"]
        assert refresh["status"] == "ready" and refresh["assignee"] == "qa"
        assert refresh["workspace_path"] == str(workspace)


def test_workspace_head_rejects_tracked_untracked_and_hidden_changes(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("reviewed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-m", "initial",
        ],
        check=True,
        capture_output=True,
    )
    producer = {"id": "t_prod", "workspace_kind": "worktree", "workspace_path": str(repo)}
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong-repository"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "wrong-index"))
    assert REAL_WORKSPACE_HEAD(producer)
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_INDEX_FILE")
    tracked.write_text("modified\n", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace is dirty"):
        REAL_WORKSPACE_HEAD(producer)
    tracked.write_text("reviewed\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("not reviewed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace is dirty"):
        REAL_WORKSPACE_HEAD(producer)
    (repo / "untracked.txt").unlink()
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--assume-unchanged", "tracked.txt"],
        check=True,
        capture_output=True,
    )
    tracked.write_text("hidden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hidden Git index flags"):
        REAL_WORKSPACE_HEAD(producer)
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--no-assume-unchanged", "tracked.txt"],
        check=True,
        capture_output=True,
    )
    tracked.write_text("reviewed\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--skip-worktree", "tracked.txt"],
        check=True,
        capture_output=True,
    )
    tracked.write_text("also hidden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hidden Git index flags"):
        REAL_WORKSPACE_HEAD(producer)


def test_workspace_requires_git_checkout_root(tmp_path):
    _, _, workspace = make_board(tmp_path)
    nested = workspace / "nested"
    nested.mkdir()
    producer = {"id": "t_prod", "workspace_kind": "worktree", "workspace_path": str(nested)}
    with pytest.raises(ValueError, match="workspace must be the Git checkout root"):
        ENGINE["workspace"](producer)


def test_workspace_head_checks_hidden_changes_inside_submodules(tmp_path):
    child = tmp_path / "child-source"
    subprocess.run(["git", "init", str(child)], check=True, capture_output=True)
    child_file = child / "tracked.txt"
    child_file.write_text("reviewed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(child), "add", "tracked.txt"], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(child), "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-m", "child",
        ],
        check=True,
        capture_output=True,
    )
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "protocol.file.allow=always",
            "submodule", "add", str(child), "child",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-m", "superproject",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo / "child"), "update-index", "--assume-unchanged", "tracked.txt"],
        check=True,
        capture_output=True,
    )
    (repo / "child" / "tracked.txt").write_text("hidden\n", encoding="utf-8")
    producer = {"id": "t_prod", "workspace_kind": "worktree", "workspace_path": str(repo)}
    with pytest.raises(ValueError, match="hidden Git index flags"):
        REAL_WORKSPACE_HEAD(producer)


def test_reviewed_commit_resolution_requires_a_git_object(tmp_path):
    _, _, workspace = make_board(tmp_path)
    reviewed = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    subprocess.run(
        [
            "git", "-C", str(workspace), "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-m", "new head",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(workspace), "branch", reviewed[:7], "HEAD"],
        check=True,
        capture_output=True,
    )
    assert REAL_RESOLVE_REVIEWED_COMMIT("t_prod", workspace, reviewed[:7]) == reviewed
    assert REAL_RESOLVE_REVIEWED_COMMIT("t_prod", workspace, "0000000") is None


def test_reviewed_commit_resolution_rejects_ambiguous_objects(tmp_path, monkeypatch):
    _, _, workspace = make_board(tmp_path)

    def ambiguous(_task_id, _path, *args, input_text=None):
        assert args == ("rev-parse", "--disambiguate=abc1234") and input_text is None
        return f"{'a' * 40}\n{'b' * 40}\n"

    monkeypatch.setitem(REAL_RESOLVE_REVIEWED_COMMIT.__globals__, "git_output", ambiguous)
    assert REAL_RESOLVE_REVIEWED_COMMIT("t_prod", workspace, "abc1234") is None


def test_workspace_rejects_relative_persistent_path(tmp_path, monkeypatch):
    (tmp_path / "relative-worktree").mkdir()
    monkeypatch.chdir(tmp_path)
    producer = {"id": "t_prod", "workspace_kind": "worktree", "workspace_path": "relative-worktree"}
    with pytest.raises(ValueError, match="workspace is unavailable"):
        ENGINE["workspace"](producer)


def test_generated_rereview_can_start_a_second_remediation(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_oldrev", "archived", "qa", "worktree", str(workspace), None, None, None, None),
            (
                "t_fix1", "done", "engineer", "worktree", str(workspace), None,
                "ttf-remediation-t_oldrev-digest", None, None,
            ),
            ("t_rerev1", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
        ],
        [
            ("t_prod", "t_oldrev"),
            ("t_prod", "t_fix1"),
            ("t_oldrev", "t_fix1"),
            ("t_fix1", "t_rerev1"),
        ],
        [("t_oldrev", VERDICT), ("t_rerev1", VERDICT)],
    )
    result = ENGINE["reconcile"]("demo", str(home), False)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        remediation, rereview = transition_rows(conn, "t_rerev1")
        parents = {row[0] for row in conn.execute("SELECT parent_id FROM task_links WHERE child_id=?", (remediation["id"],))}
        assert result == [f"remediated t_rerev1 -> {remediation['id']} -> {rereview['id']}"]
        assert parents == {"t_fix1", "t_rerev1"}


def test_remediation_depth_ignores_sibling_branch_repairs(tmp_path):
    _, db_path, workspace = make_board(tmp_path)
    tasks = [
        ("t_integration", "done", "engineer", "worktree", str(workspace), None, None, None, None),
        ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
    ]
    links = [("t_integration", "t_review")]
    for index in range(3):
        fix = f"t_sibling{index}"
        tasks.append(
            (
                fix, "done", "engineer", "worktree", str(workspace), None,
                f"ttf-remediation-t_branch{index}-digest", None, None,
            )
        )
        links.append((fix, "t_integration"))
    add_tasks(db_path, tasks, links)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert ENGINE["remediation_depth"](conn, "t_review") == 0


def test_human_gate_is_not_automated(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, "needs_input", None),
        ],
        [("t_prod", "t_review")],
        [("t_review", VERDICT)],
    )
    assert ENGINE["reconcile"]("demo", str(home), False) == []


def test_retained_engine_gate_does_not_reserve_the_checkout(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            (
                "t_gate", "blocked", "orchestrator", "dir", str(workspace), None,
                "ttf-review-gate-t_old-digest", "needs_input", None,
            ),
            ("t_gated", "todo", "release", "dir", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review"), ("t_prod", "t_gate"), ("t_gate", "t_gated")],
        [("t_review", VERDICT)],
    )

    result = ENGINE["reconcile"]("demo", str(home), False)
    assert len(result) == 1 and result[0].startswith("remediated t_review -> ")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT status FROM tasks WHERE id='t_gate'").fetchone()[0] == "blocked"
        assert conn.execute(
            "SELECT COUNT(*) FROM task_links WHERE parent_id='t_gate' AND child_id='t_gated'"
        ).fetchone()[0] == 1


def test_remediation_cap_routes_to_one_sticky_owner_gate(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    tasks = [("t_root", "done", "engineer", "worktree", str(workspace), None, None, None, None)]
    links = []
    comments = []
    parent = "t_root"
    for index in range(1, 4):
        review = f"t_rev{index}"
        remediation = f"t_fix{index}"
        tasks.extend(
            [
                (review, "archived", "qa", "worktree", str(workspace), None, None, None, None),
                (
                    remediation, "done", "engineer", "worktree", str(workspace), None,
                    f"ttf-remediation-{review}-digest", None, None,
                ),
            ]
        )
        links.extend(((parent, review), (parent, remediation), (review, remediation)))
        comments.append((review, VERDICT))
        parent = remediation
    tasks.extend(
        [
            ("t_final", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            ("t_next", "todo", "release", "worktree", str(workspace), None, None, None, None),
        ]
    )
    links.extend(((parent, "t_final"), ("t_final", "t_next")))
    comments.append(("t_final", VERDICT))
    add_tasks(db_path, tasks, links, comments)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO kanban_notify_subs "
            "(task_id, platform, chat_id, thread_id, user_id, notifier_profile, created_at) "
            "VALUES ('t_final', 'telegram', 'cap-chat', '', 'owner', 'orchestrator', 1)"
        )
    result = ENGINE["reconcile"]("demo", str(home), False, "ops-owner")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        gate = conn.execute("SELECT * FROM tasks WHERE idempotency_key LIKE 'ttf-review-gate-t_final-%'").fetchone()
        parents = {row[0] for row in conn.execute("SELECT parent_id FROM task_links WHERE child_id=?", (gate["id"],))}
        links = {tuple(row) for row in conn.execute("SELECT parent_id, child_id FROM task_links")}
        assert result == [f"gated t_final -> {gate['id']} after 3 remediation generations"]
        assert gate["status"] == "blocked" and gate["block_kind"] == "needs_input"
        assert gate["block_recurrences"] == 1
        assert gate["assignee"] == "ops-owner" and gate["created_by"] == "ttf-transition-engine"
        assert parents == {"t_fix3"}
        assert conn.execute("SELECT kind FROM task_events WHERE task_id=? ORDER BY id DESC", (gate["id"],)).fetchone()[0] == "blocked"
        created_event = conn.execute(
            "SELECT id FROM task_events WHERE task_id=? AND kind='created'", (gate["id"],)
        ).fetchone()[0]
        blocked_event = conn.execute(
            "SELECT id FROM task_events WHERE task_id=? AND kind='blocked'", (gate["id"],)
        ).fetchone()[0]
        subscription_cursor = conn.execute(
            "SELECT last_event_id FROM kanban_notify_subs WHERE task_id=? AND chat_id='cap-chat'", (gate["id"],)
        ).fetchone()[0]
        assert subscription_cursor == created_event < blocked_event
        assert conn.execute("SELECT status FROM tasks WHERE id='t_final'").fetchone()[0] == "archived"
        assert (gate["id"], "t_next") in links and ("t_final", "t_next") not in links
    assert ENGINE["reconcile"]("demo", str(home), False, "ops-owner") == []


def test_stale_refresh_cap_routes_to_owner_gate(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    tasks = [("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None)]
    links = []
    comments = []
    parent = "t_prod"
    for index in range(4):
        review = f"t_refresh{index}"
        key = None if index == 0 else f"ttf-refresh-review-t_refresh{index - 1}-digest"
        status = "blocked" if index == 3 else "archived"
        tasks.append((review, status, "qa", "worktree", str(workspace), None, key, None, None))
        links.append((parent, review))
        comments.append((review, VERDICT))
        parent = review
    tasks.append(("t_next", "todo", "release", "worktree", str(workspace), None, None, None, None))
    links.append((parent, "t_next"))
    add_tasks(db_path, tasks, links, comments)
    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", lambda task: "def5678")

    result = ENGINE["reconcile"]("demo", str(home), False, "ops-owner")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        gate = conn.execute(
            "SELECT * FROM tasks WHERE idempotency_key LIKE 'ttf-review-gate-t_refresh3-%'"
        ).fetchone()
        assert result == [f"gated stale review t_refresh3 -> {gate['id']} after 3 refreshes"]
        assert gate["status"] == "blocked" and gate["block_kind"] == "needs_input"
        assert conn.execute(
            "SELECT COUNT(*) FROM task_links WHERE parent_id=? AND child_id='t_next'", (gate["id"],)
        ).fetchone()[0] == 1


def test_stale_refresh_preserves_remediation_generation_cap(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    tasks = [("t_root", "done", "engineer", "worktree", str(workspace), None, None, None, None)]
    links = []
    comments = []
    parent = "t_root"
    for index in range(1, 4):
        review = f"t_rev{index}"
        remediation = f"t_fix{index}"
        tasks.extend(
            [
                (review, "archived", "qa", "worktree", str(workspace), None, None, None, None),
                (
                    remediation, "done", "engineer", "worktree", str(workspace), None,
                    f"ttf-remediation-{review}-digest", None, None,
                ),
            ]
        )
        links.extend(((parent, review), (parent, remediation), (review, remediation)))
        comments.append((review, VERDICT))
        parent = remediation
    tasks.extend(
        [
            ("t_stale", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            ("t_next", "todo", "release", "worktree", str(workspace), None, None, None, None),
        ]
    )
    links.extend(((parent, "t_stale"), ("t_stale", "t_next")))
    comments.append(("t_stale", VERDICT))
    add_tasks(db_path, tasks, links, comments)
    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", lambda task: "def5678")

    first = ENGINE["reconcile"]("demo", str(home), False, "ops-owner")
    assert len(first) == 1 and first[0].startswith("refreshed stale review t_stale -> ")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        refresh = conn.execute(
            "SELECT * FROM tasks WHERE idempotency_key LIKE 'ttf-refresh-review-t_stale-%'"
        ).fetchone()
        conn.execute("UPDATE tasks SET status='blocked' WHERE id=?", (refresh["id"],))
        conn.execute(
            "INSERT INTO task_comments(task_id, author, body) VALUES (?, 'qa', ?)",
            (refresh["id"], VERDICT.replace("abc1234", "def5678")),
        )

    second = ENGINE["reconcile"]("demo", str(home), False, "ops-owner")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        gate = conn.execute(
            "SELECT * FROM tasks WHERE idempotency_key LIKE ?",
            (f"ttf-review-gate-{refresh['id']}-%",),
        ).fetchone()
        assert second == [f"gated {refresh['id']} -> {gate['id']} after 3 remediation generations"]
        assert conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE idempotency_key LIKE ?",
            (f"ttf-remediation-{refresh['id']}-%",),
        ).fetchone()[0] == 0


def test_one_failed_review_does_not_starve_the_next(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    tasks = []
    links = []
    comments = []
    for producer, review, child in (("t_p111", "t_a111", "t_c111"), ("t_p222", "t_b222", "t_c222")):
        tasks.extend(
            [
                (producer, "done", "engineer", "worktree", str(workspace), None, None, None, None),
                (review, "blocked", "qa", "worktree", str(workspace), None, None, None, None),
                (child, "todo", "release", "worktree", str(workspace), None, None, None, None),
            ]
        )
        links.extend(((producer, review), (review, child)))
        comments.append((review, VERDICT))
    add_tasks(db_path, tasks, links, comments)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tasks SET workspace_kind='scratch' WHERE id='t_p111'")
    result = ENGINE["reconcile"]("demo", str(home), False)

    assert result[0] == "error: t_a111: producer t_p111 has no persistent workspace"
    assert result[1].startswith("remediated t_b222 -> ")


def test_shared_workspace_defers_until_fresh_verdict(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review1", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            ("t_review2", "blocked", "security", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review1"), ("t_prod", "t_review2")],
        [("t_review1", VERDICT), ("t_review2", VERDICT)],
    )
    head_checks = 0
    head = "abc1234"

    def checked_head(task):
        nonlocal head_checks, head
        head_checks += 1
        return head

    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", checked_head)

    first = ENGINE["reconcile"]("demo", str(home), False)
    assert len(first) == 1 and first[0].startswith("remediated t_review1 -> ")
    assert head_checks == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT status FROM tasks WHERE id='t_review2'").fetchone()[0] == "blocked"
        assert conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE idempotency_key LIKE 'ttf-remediation-t_review2-%'"
        ).fetchone()[0] == 0
        conn.execute(
            "UPDATE tasks SET status='done' WHERE idempotency_key LIKE 'ttf-remediation-t_review1-%'"
        )

    assert ENGINE["reconcile"]("demo", str(home), False) == []
    assert head_checks == 1
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tasks SET status='done' WHERE created_by='ttf-transition-engine'")

    head = "def5678"
    refresh_result = ENGINE["reconcile"]("demo", str(home), False)
    assert len(refresh_result) == 1 and refresh_result[0].startswith("refreshed stale review t_review2 -> ")
    assert head_checks == 2
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        refresh = conn.execute(
            "SELECT * FROM tasks WHERE idempotency_key LIKE 'ttf-refresh-review-t_review2-%'"
        ).fetchone()
        assert refresh["status"] == "ready" and refresh["assignee"] == "security"
        assert "clean checkout is now `def5678`" in refresh["body"]
        assert conn.execute("SELECT status FROM tasks WHERE id='t_review2'").fetchone()[0] == "archived"
        assert conn.execute(
            "SELECT COUNT(*) FROM task_links WHERE parent_id='t_review2' AND child_id=?", (refresh["id"],)
        ).fetchone()[0] == 1
        conn.execute("UPDATE tasks SET status='blocked' WHERE id=?", (refresh["id"],))
        conn.execute(
            "INSERT INTO task_comments(task_id, author, body) VALUES (?, 'security', ?)",
            (refresh["id"], VERDICT.replace("abc1234", "def5678")),
        )

    remediated = ENGINE["reconcile"]("demo", str(home), False)
    assert len(remediated) == 1 and remediated[0].startswith(f"remediated {refresh['id']} -> ")
    assert head_checks == 3


@pytest.mark.parametrize("status", ["todo", "ready", "running", "review"])
def test_runnable_sibling_reviewer_defers_before_head_probe(tmp_path, monkeypatch, status):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_rejected", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            ("t_sibling", status, "security", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_rejected"), ("t_prod", "t_sibling")],
        [("t_rejected", VERDICT)],
    )

    def unexpected_head(_task):
        raise AssertionError("an executable sibling must reserve the checkout before probing HEAD")

    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", unexpected_head)
    assert ENGINE["reconcile"]("demo", str(home), False) == []


def test_shared_checkout_worker_defers_without_unrelated_task_deadlock(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_rejected", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            ("t_other_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_worker", "ready", "developer", "dir", str(workspace), None, None, None, None),
            ("t_scratch", "running", "researcher", "scratch", None, None, None, None, None),
            ("t_waiting", "todo", "release", "dir", str(workspace), None, None, None, None),
            ("t_triage", "triage", "orchestrator", "dir", str(workspace), None, None, None, None),
            ("t_invalid", "running", "researcher", "dir", str(other_workspace), None, None, None, None),
        ],
        [
            ("t_prod", "t_rejected"),
            ("t_other_prod", "t_worker"),
            ("t_prod", "t_waiting"),
            ("t_rejected", "t_waiting"),
        ],
        [("t_rejected", VERDICT)],
    )
    head_checks = 0

    def checked_head(_task):
        nonlocal head_checks
        head_checks += 1
        return "abc1234"

    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", checked_head)
    assert ENGINE["reconcile"]("demo", str(home), False) == []
    assert head_checks == 0

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tasks SET status='done' WHERE id='t_worker'")

    result = ENGINE["reconcile"]("demo", str(home), False)
    assert len(result) == 1 and result[0].startswith("remediated t_rejected -> ")
    assert head_checks == 1


def test_dry_run_reserves_one_shared_workspace_lane(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review1", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            ("t_review2", "blocked", "security", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review1"), ("t_prod", "t_review2")],
        [("t_review1", VERDICT), ("t_review2", VERDICT)],
    )

    assert ENGINE["reconcile"]("demo", str(home), True) == [
        "would remediate t_review1 with 0 downstream tasks",
        "would defer t_review2 because workspace lane is busy",
    ]


def test_legacy_transition_in_same_checkout_defers_before_head_probe(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    nested = workspace / "nested"
    nested.mkdir()
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            (
                "t_legacy", "running", "engineer", "dir", str(nested), None,
                "ttf-remediation-t_other", None, None,
            ),
        ],
        [("t_prod", "t_review")],
        [("t_review", VERDICT)],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tasks SET created_by='orchestrator' WHERE id='t_legacy'")

    def unexpected_head(_task):
        raise AssertionError("busy lanes must defer before probing HEAD")

    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", unexpected_head)
    assert ENGINE["reconcile"]("demo", str(home), False) == []


def test_unverifiable_active_transition_fails_closed_before_head_probe(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    not_git = tmp_path / "not-git"
    not_git.mkdir()
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
            (
                "t_broken", "running", "engineer", "dir", str(not_git), None,
                "ttf-remediation-t_other", None, None,
            ),
        ],
        [("t_prod", "t_review")],
        [("t_review", VERDICT)],
    )

    def unexpected_head(_task):
        raise AssertionError("unverifiable active lanes must fail before probing HEAD")

    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", unexpected_head)
    assert ENGINE["reconcile"]("demo", str(home), False) == [
        "error: t_review: active transition t_broken has an unverifiable workspace"
    ]


def test_unassigned_review_isolated_from_later_work(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod1", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_a_review", "blocked", None, "worktree", str(workspace), None, None, None, None),
            ("t_prod2", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_b_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod1", "t_a_review"), ("t_prod2", "t_b_review")],
        [("t_a_review", VERDICT), ("t_b_review", VERDICT)],
    )

    result = ENGINE["reconcile"]("demo", str(home), False)
    assert len(result) == 1 and result[0].startswith("remediated t_b_review -> ")


def test_atomic_failure_rolls_back_every_transition_write(tmp_path, monkeypatch):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review")],
        [("t_review", VERDICT)],
    )
    original = ENGINE["insert_task"]
    calls = 0

    def fail_on_second_insert(*args, **kwargs):
        nonlocal calls
        calls += 1
        task_id = original(*args, **kwargs)
        if calls == 2:
            raise RuntimeError("simulated crash")
        return task_id

    monkeypatch.setitem(ENGINE["apply_transition"].__globals__, "insert_task", fail_on_second_insert)
    assert ENGINE["reconcile"]("demo", str(home), False) == ["error: t_review: simulated crash"]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE created_by='ttf-transition-engine'").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM tasks WHERE id='t_review'").fetchone()[0] == "blocked"
        assert conn.execute("SELECT COUNT(*) FROM task_links WHERE parent_id='t_prod' AND child_id='t_review'").fetchone()[0] == 1


def test_conflicting_transition_is_not_reused_or_archived(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
                (
                    "t_old_fix", "todo", "engineer", "worktree", str(workspace), None,
                    "ttf-remediation-t_review", None, None,
                ),
        ],
        [("t_prod", "t_review"), ("t_prod", "t_old_fix"), ("t_review", "t_old_fix")],
        [("t_review", VERDICT)],
    )
    assert ENGINE["reconcile"]("demo", str(home), False) == [
        "error: t_review: review t_review already has an active or conflicting transition"
    ]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT status FROM tasks WHERE id='t_old_fix'").fetchone()[0] == "todo"
        assert conn.execute("SELECT status FROM tasks WHERE id='t_review'").fetchone()[0] == "blocked"


def test_ephemeral_producer_workspace_fails_closed(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "scratch", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "scratch", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review")],
        [("t_review", VERDICT)],
    )
    assert ENGINE["reconcile"]("demo", str(home), True) == [
        "error: t_review: producer t_prod has no persistent workspace"
    ]


def test_board_lock_skips_overlapping_reconcile(tmp_path):
    home, db_path, _ = make_board(tmp_path)
    with ENGINE["board_lock"](db_path):
        assert ENGINE["reconcile"]("demo", str(home), False) == [ENGINE["LOCK_BUSY"]]


def test_runtime_errors_are_emitted_once_until_resolved(tmp_path):
    state = tmp_path / "kanban.db"
    error = "error: t_review: malformed graph"
    assert ENGINE["dedupe_runtime_errors"](state, [error]) == [error]
    assert ENGINE["dedupe_runtime_errors"](state, [error]) == []
    assert ENGINE["dedupe_runtime_errors"](state, []) == []
    assert ENGINE["dedupe_runtime_errors"](state, [error]) == [error]


def test_deduplicated_runtime_error_keeps_failing_exit_status(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "scratch", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "scratch", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review")],
        [("t_review", VERDICT)],
    )
    command = [
        sys.executable, str(ROOT / "scripts" / "kanban-transition-engine.py"),
        "--board", "demo", "--home", str(home),
    ]

    first = subprocess.run(command, text=True, capture_output=True)
    second = subprocess.run(command, text=True, capture_output=True)
    assert first.returncode == second.returncode == 1
    assert "no persistent workspace" in first.stdout
    assert second.stdout == ""


def test_default_board_path(tmp_path):
    assert ENGINE["board_db_path"](str(tmp_path), "Default") == tmp_path / "kanban.db"


@pytest.mark.parametrize("reserved", ["#", "?"])
def test_read_only_database_uri_encodes_reserved_path_characters(tmp_path, reserved):
    scope = tmp_path / f"scope{reserved}tail"
    home, db_path, workspace = make_board(scope)
    add_tasks(
        db_path,
        [
            ("t_prod", "done", "engineer", "worktree", str(workspace), None, None, None, None),
            ("t_review", "blocked", "qa", "worktree", str(workspace), None, None, None, None),
        ],
        [("t_prod", "t_review")],
        [("t_review", VERDICT)],
    )

    assert ENGINE["reconcile"]("demo", str(home), True) == [
        "would remediate t_review with 0 downstream tasks"
    ]
    assert not (tmp_path / "scope").exists()


def test_installer_rejects_missing_board_before_writes(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    hermes = fake_bin / "hermes"
    hermes.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hermes.chmod(0o755)
    home = tmp_path / "home"
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "HERMES_HOME": str(home)}
    env.pop("HERMES_KANBAN_DB", None)
    env.pop("HERMES_KANBAN_HOME", None)

    result = subprocess.run(
        [str(ROOT / "scripts" / "enable-kanban-autopilot.sh"), "--profile", "default", "missing"],
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 2
    assert "Kanban board not found" in result.stderr
    assert not (home / "scripts").exists()


def test_installer_requires_explicit_legacy_takeover(tmp_path):
    home, _, _ = make_board(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
if [ "$*" = "-p orchestrator cron list --all" ]; then
  printf '%s\n' '  aaa111 [active]' '    Name:      demo-graph-governor'
fi
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "HERMES_HOME": str(home)}
    result = subprocess.run(
        [str(ROOT / "scripts" / "enable-kanban-autopilot.sh"), "--profile", "orchestrator", "demo"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 1
    assert "migrate every reviewer" in result.stderr.lower()
    assert not (home / "profiles" / "orchestrator" / "scripts").exists()


def test_installer_pauses_legacy_and_resumes_exact_job(tmp_path):
    home, db_path, workspace = make_board(tmp_path)
    # A malformed legacy review must not prevent installing the recovery engine.
    add_tasks(
        db_path,
        [("t_legacy", "blocked", "qa", "worktree", str(workspace), None, None, None, None)],
        comments=[("t_legacy", VERDICT)],
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "hermes.log"
    state = tmp_path / "cron-active"
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$HERMES_TEST_LOG"
if [ "$*" = "-p orchestrator cron resume bbb222" ]; then
  : > "$HERMES_TEST_STATE"
fi
if [ "$*" = "-p orchestrator cron list --all" ]; then
  current=paused
  [ -f "$HERMES_TEST_STATE" ] && current=active
  printf '%s\n' \
    '  aaa111 [active]' \
    '    Name:      demo-graph-governor' \
    '  aaa222 [active]' \
    '    Name:      demo-graph-governor' \
    "  bbb222 [$current]" \
    '    Name:      ttf-demo-transition-engine'
fi
if [ "$*" = "-p default cron list --all" ]; then
  printf '%s\n' '  ccc333 [active]' '    Name:      ttf-demo-graph-governor'
fi
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HERMES_HOME": str(home),
        "HERMES_TEST_LOG": str(log),
        "HERMES_TEST_STATE": str(state),
    }
    env.pop("HERMES_KANBAN_DB", None)
    env.pop("HERMES_KANBAN_HOME", None)

    result = subprocess.run(
        [
            str(ROOT / "scripts" / "enable-kanban-autopilot.sh"),
            "--profile", "Orchestrator", "--replace-legacy", "Demo",
        ],
        text=True,
        capture_output=True,
        env=env,
    )

    commands = log.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "-p orchestrator cron pause aaa111" in commands
    assert "-p orchestrator cron pause aaa222" in commands
    assert "-p default cron pause ccc333" in commands
    assert "-p orchestrator cron edit bbb222 --schedule every 1m --script ttf-demo-transition-engine.py --no-agent --repeat 0" in commands
    assert "--monitor-script  --monitor-url" in commands
    assert "-p orchestrator cron resume bbb222" in commands
    assert " cron create " not in commands
    wrapper = home / "profiles" / "orchestrator" / "scripts" / "ttf-demo-transition-engine.py"
    core = home / "profiles" / "orchestrator" / "scripts" / "ttf-demo-transition-engine-core.py"
    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert core.read_bytes() == (ROOT / "scripts" / "kanban-transition-engine.py").read_bytes()
    assert str(core) in wrapper_text
    assert "sys.executable" in wrapper_text
    assert "'--owner-profile', 'orchestrator'" in wrapper_text
    assert f"os.environ['HERMES_KANBAN_DB'] = '{db_path}'" in wrapper_text
    assert "HERMES_KANBAN_TASK" in wrapper_text and "os.environ.pop" in wrapper_text
    assert list(wrapper.parent.glob(".ttf-demo-engine-rollback.*")) == []


def test_installer_keeps_engine_copies_isolated_per_board(tmp_path):
    home, demo_db, _ = make_board(tmp_path)
    other_db = home / "kanban" / "boards" / "other" / "kanban.db"
    other_db.parent.mkdir(parents=True)
    with sqlite3.connect(demo_db) as source, sqlite3.connect(other_db) as destination:
        source.backup(destination)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
if [ "$*" = "-p orchestrator cron list --all" ]; then
  printf '%s\n' \
    '  aaa111 [active]' '    Name:      ttf-demo-transition-engine' \
    '  bbb222 [active]' '    Name:      ttf-other-transition-engine'
fi
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "HERMES_HOME": str(home)}
    for key in ("HERMES_KANBAN_DB", "HERMES_KANBAN_HOME", "HERMES_KANBAN_TASK"):
        env.pop(key, None)
    installer = str(ROOT / "scripts" / "enable-kanban-autopilot.sh")

    first = subprocess.run(
        [installer, "--profile", "orchestrator", "demo"], text=True, capture_output=True, env=env
    )
    scripts = home / "profiles" / "orchestrator" / "scripts"
    demo_core = scripts / "ttf-demo-transition-engine-core.py"
    demo_wrapper = scripts / "ttf-demo-transition-engine.py"
    assert first.returncode == 0, first.stderr
    assert demo_core.read_bytes() == (ROOT / "scripts" / "kanban-transition-engine.py").read_bytes()
    demo_core.write_text("demo sentinel\n", encoding="utf-8")
    demo_wrapper_before = demo_wrapper.read_bytes()

    second = subprocess.run(
        [installer, "--profile", "orchestrator", "other"], text=True, capture_output=True, env=env
    )
    other_core = scripts / "ttf-other-transition-engine-core.py"
    other_wrapper = scripts / "ttf-other-transition-engine.py"
    assert second.returncode == 0, second.stderr
    assert demo_core.read_text(encoding="utf-8") == "demo sentinel\n"
    assert demo_wrapper.read_bytes() == demo_wrapper_before
    assert other_core.read_bytes() == (ROOT / "scripts" / "kanban-transition-engine.py").read_bytes()
    assert str(other_core) in other_wrapper.read_text(encoding="utf-8")
    assert str(demo_core) not in other_wrapper.read_text(encoding="utf-8")


def test_installer_leaves_legacy_active_when_replacement_fails(tmp_path):
    home, _, _ = make_board(tmp_path)
    scripts = home / "profiles" / "orchestrator" / "scripts"
    scripts.mkdir(parents=True)
    old_wrapper = scripts / "ttf-demo-transition-engine.py"
    old_core = scripts / "ttf-demo-transition-engine-core.py"
    old_wrapper.write_text("old wrapper\n", encoding="utf-8")
    old_core.write_text("old core\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "hermes.log"
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$HERMES_TEST_LOG"
if [ "$*" = "-p orchestrator cron list --all" ]; then
  printf '%s\n' \
    '  aaa111 [active]' '    Name:      demo-graph-governor' \
    '  bbb222 [paused]' '    Name:      ttf-demo-transition-engine'
fi
case "$*" in "-p orchestrator cron edit "*) exit 1 ;; esac
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HERMES_HOME": str(home),
        "HERMES_TEST_LOG": str(log),
    }
    result = subprocess.run(
        [
            str(ROOT / "scripts" / "enable-kanban-autopilot.sh"),
            "--profile", "orchestrator", "--replace-legacy", "demo",
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    commands = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "cron pause aaa111" not in commands
    assert old_wrapper.read_text(encoding="utf-8") == "old wrapper\n"
    assert old_core.read_text(encoding="utf-8") == "old core\n"
    assert list(scripts.glob(".ttf-demo-engine-rollback.*")) == []


def test_installer_restores_active_engine_when_interrupted(tmp_path):
    home, _, _ = make_board(tmp_path)
    scripts = home / "profiles" / "orchestrator" / "scripts"
    scripts.mkdir(parents=True)
    old_wrapper = scripts / "ttf-demo-transition-engine.py"
    old_core = scripts / "ttf-demo-transition-engine-core.py"
    old_wrapper.write_text("signal old wrapper\n", encoding="utf-8")
    old_core.write_text("signal old core\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "hermes.log"
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$HERMES_TEST_LOG"
if [ "$*" = "-p orchestrator cron list --all" ]; then
  printf '%s\n' '  bbb222 [active]' '    Name:      ttf-demo-transition-engine'
fi
case "$*" in
  "-p orchestrator cron edit "*) kill -TERM "$PPID"; sleep 0.1; exit 143 ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)

    result = subprocess.run(
        [
            str(ROOT / "scripts" / "enable-kanban-autopilot.sh"),
            "--profile", "orchestrator", "demo",
        ],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HERMES_HOME": str(home),
            "HERMES_TEST_LOG": str(log),
        },
    )

    commands = log.read_text(encoding="utf-8")
    assert result.returncode == 143
    assert "cron pause bbb222" in commands and "cron resume bbb222" in commands
    assert old_wrapper.read_text(encoding="utf-8") == "signal old wrapper\n"
    assert old_core.read_text(encoding="utf-8") == "signal old core\n"
    assert list(scripts.glob(".ttf-demo-engine-rollback.*")) == []


def test_installer_rolls_back_replacement_when_activation_cannot_be_verified(tmp_path):
    home, _, _ = make_board(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "hermes.log"
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$HERMES_TEST_LOG"
if [ "$*" = "-p orchestrator cron list --all" ]; then
  printf '%s\n' \
    '  aaa111 [active]' '    Name:      demo-graph-governor' \
    '  bbb222 [paused]' '    Name:      ttf-demo-transition-engine'
fi
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    result = subprocess.run(
        [
            str(ROOT / "scripts" / "enable-kanban-autopilot.sh"),
            "--profile", "orchestrator", "--replace-legacy", "demo",
        ],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HERMES_HOME": str(home),
            "HERMES_TEST_LOG": str(log),
        },
    )
    commands = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "cron resume bbb222" in commands and "cron pause bbb222" in commands
    assert "cron pause aaa111" not in commands
    scripts = home / "profiles" / "orchestrator" / "scripts"
    assert not (scripts / "ttf-demo-transition-engine.py").exists()
    assert not (scripts / "ttf-demo-transition-engine-core.py").exists()
    assert list(scripts.glob(".ttf-demo-engine-rollback.*")) == []


def test_installer_rolls_back_replacement_when_verification_list_fails(tmp_path):
    home, _, _ = make_board(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "hermes.log"
    resumed = tmp_path / "resumed"
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$HERMES_TEST_LOG"
if [ "$*" = "-p orchestrator cron resume bbb222" ]; then
  : > "$HERMES_TEST_STATE"
fi
if [ "$*" = "-p orchestrator cron list --all" ]; then
  [ -f "$HERMES_TEST_STATE" ] && exit 1
  printf '%s\n' \
    '  aaa111 [active]' '    Name:      demo-graph-governor' \
    '  bbb222 [paused]' '    Name:      ttf-demo-transition-engine'
fi
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    result = subprocess.run(
        [
            str(ROOT / "scripts" / "enable-kanban-autopilot.sh"),
            "--profile", "orchestrator", "--replace-legacy", "demo",
        ],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HERMES_HOME": str(home),
            "HERMES_TEST_LOG": str(log),
            "HERMES_TEST_STATE": str(resumed),
        },
    )
    commands = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "cron resume bbb222" in commands and "cron pause bbb222" in commands
    assert "cron pause aaa111" not in commands


def test_installer_restores_duplicate_current_jobs_when_pause_fails(tmp_path):
    home, _, _ = make_board(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "hermes.log"
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$HERMES_TEST_LOG"
if [ "$*" = "-p orchestrator cron list --all" ]; then
  printf '%s\n' \
    '  aaa111 [active]' '    Name:      demo-graph-governor' \
    '  bbb222 [active]' '    Name:      ttf-demo-transition-engine' \
    '  ccc333 [active]' '    Name:      ttf-demo-transition-engine' \
    '  ddd444 [active]' '    Name:      ttf-demo-transition-engine'
fi
[ "$*" = "-p orchestrator cron pause ddd444" ] && exit 1
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    result = subprocess.run(
        [
            str(ROOT / "scripts" / "enable-kanban-autopilot.sh"),
            "--profile", "orchestrator", "--replace-legacy", "demo",
        ],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HERMES_HOME": str(home),
            "HERMES_TEST_LOG": str(log),
        },
    )
    commands = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "cron pause ccc333" in commands and "cron pause ddd444" in commands
    assert "cron resume ccc333" in commands and "cron resume ddd444" in commands
    assert "cron pause aaa111" not in commands


def test_installer_restores_jobs_when_a_legacy_pause_fails(tmp_path):
    home, _, _ = make_board(tmp_path)
    scripts = home / "profiles" / "orchestrator" / "scripts"
    scripts.mkdir(parents=True)
    old_wrapper = scripts / "ttf-demo-transition-engine.py"
    old_core = scripts / "ttf-demo-transition-engine-core.py"
    old_wrapper.write_text("late old wrapper\n", encoding="utf-8")
    old_core.write_text("late old core\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "hermes.log"
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$HERMES_TEST_LOG"
if [ "$*" = "-p orchestrator cron list --all" ]; then
  printf '%s\n' \
    '  aaa111 [active]' '    Name:      demo-graph-governor' \
    '  aaa222 [active]' '    Name:      ttf-demo-graph-governor' \
    '  bbb222 [active]' '    Name:      ttf-demo-transition-engine'
fi
[ "$*" = "-p orchestrator cron pause aaa111" ] && exit 1
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HERMES_HOME": str(home),
        "HERMES_TEST_LOG": str(log),
    }
    result = subprocess.run(
        [
            str(ROOT / "scripts" / "enable-kanban-autopilot.sh"),
            "--profile", "orchestrator", "--replace-legacy", "demo",
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    commands = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "cron pause aaa111" in commands and "cron pause aaa222" in commands
    assert "cron resume aaa111" in commands and "cron resume aaa222" in commands
    assert "cron pause bbb222" in commands and "cron resume bbb222" in commands
    assert old_wrapper.read_text(encoding="utf-8") == "late old wrapper\n"
    assert old_core.read_text(encoding="utf-8") == "late old core\n"
    assert list(scripts.glob(".ttf-demo-engine-rollback.*")) == []


def test_local_install_restores_previous_plugin_when_enable_fails(tmp_path):
    home = tmp_path / "home"
    old_plugin = home / "plugins" / "thinktofinish-company"
    old_plugin.mkdir(parents=True)
    (old_plugin / "sentinel").write_text("old", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    hermes = fake_bin / "hermes"
    hermes.write_text(
        """#!/bin/sh
case "$*" in "-p default plugins enable thinktofinish-company --no-allow-tool-override") exit 1 ;; esac
exit 0
""",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    result = subprocess.run(
        [str(ROOT / "scripts" / "install-local.sh"), "--profile", "default"],
        text=True,
        capture_output=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "HERMES_HOME": str(home)},
    )
    assert result.returncode != 0
    assert (old_plugin / "sentinel").read_text(encoding="utf-8") == "old"

    fresh_home = tmp_path / "fresh-home"
    fresh = subprocess.run(
        [str(ROOT / "scripts" / "install-local.sh"), "--profile", "default"],
        text=True,
        capture_output=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "HERMES_HOME": str(fresh_home)},
    )
    assert fresh.returncode != 0
    assert not (fresh_home / "plugins" / "thinktofinish-company").exists()
