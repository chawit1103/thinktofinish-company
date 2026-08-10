import os
import runpy
import sqlite3
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
ENGINE = runpy.run_path(str(ROOT / "scripts" / "kanban-transition-engine.py"))
VERDICT = '{"ttf_review":{"decision":"changes_requested","reviewed_commit":"abc1234","findings":["Add a regression test"]}}'
APPROVED = '{"ttf_review":{"decision":"approved","reviewed_commit":"abc1234","findings":[]}}'


@pytest.fixture(autouse=True)
def stable_test_head(monkeypatch):
    monkeypatch.setitem(ENGINE["transition_plan"].__globals__, "workspace_head", lambda task: "abc1234")


def make_board(tmp_path, board="demo"):
    home = tmp_path / "hermes"
    workspace = home / "worktree"
    workspace.mkdir(parents=True)
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


def test_reviewed_commit_must_match_workspace_head(tmp_path, monkeypatch):
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
    assert ENGINE["reconcile"]("demo", str(home), True) == [
        "error: t_review: reviewed commit def5678 does not match producer t_prod HEAD abc1234"
    ]


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


def test_default_board_path(tmp_path):
    assert ENGINE["board_db_path"](str(tmp_path), "Default") == tmp_path / "kanban.db"


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
    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert "sys.executable" in wrapper_text
    assert "'--owner-profile', 'orchestrator'" in wrapper_text
    assert f"os.environ['HERMES_KANBAN_DB'] = '{db_path}'" in wrapper_text
    assert "HERMES_KANBAN_TASK" in wrapper_text and "os.environ.pop" in wrapper_text


def test_installer_leaves_legacy_active_when_replacement_fails(tmp_path):
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
    assert "cron pause bbb222" not in commands


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
