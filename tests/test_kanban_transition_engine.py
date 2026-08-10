import runpy
import sqlite3
from pathlib import Path


ENGINE = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "kanban-transition-engine.py"))


def test_request_changes_creates_repair_and_rewires_downstream(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    db_path = home / "kanban" / "boards" / "demo" / "kanban.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tasks (id TEXT, status TEXT, assignee TEXT, workspace_path TEXT);
            CREATE TABLE task_links (parent_id TEXT, child_id TEXT);
            CREATE TABLE task_comments (id INTEGER PRIMARY KEY, task_id TEXT, body TEXT);
            """
        )
        conn.executemany(
            "INSERT INTO tasks VALUES (?, ?, ?, ?)",
            [
                ("t_producer", "done", "engineer", "/worktree"),
                ("t_review", "blocked", "qa-reviewer", "/worktree"),
                ("t_downstream", "todo", "qa-reviewer", "/worktree"),
            ],
        )
        conn.executemany("INSERT INTO task_links VALUES (?, ?)", [("t_producer", "t_review"), ("t_review", "t_downstream")])
        conn.execute(
            "INSERT INTO task_comments(task_id, body) VALUES (?, ?)",
            ("t_review", '{"ttf_review":{"decision":"changes_requested","reviewed_commit":"abc1234","findings":["Add a regression test"]}}'),
        )

    calls = []

    def fake_command(board, selected_home, *args, capture=False):
        calls.append(args)
        if args[0] == "create":
            return '{"id":"t_remediation"}' if len([call for call in calls if call[0] == "create"]) == 1 else '{"id":"t_rereview"}'
        return ""

    monkeypatch.setitem(ENGINE["reconcile"].__globals__, "command", fake_command)
    result = ENGINE["reconcile"]("demo", str(home), False)

    assert result == ["remediated t_review -> t_remediation -> t_rereview"]
    assert ("unlink", "t_review", "t_downstream") in calls
    assert ("link", "t_rereview", "t_downstream") in calls
    assert ("archive", "t_review") in calls
