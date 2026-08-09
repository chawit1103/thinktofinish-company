from __future__ import annotations

import json
from collections import deque
from typing import Any

from .db import connect
from .safety import sanitize_metadata


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(sanitize_metadata(value or {}), ensure_ascii=False, sort_keys=True)


def record_node(project: str, node_type: str, node_id: str, title: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO trace_nodes(project,node_type,node_id,title,metadata_json)
            VALUES(?,?,?,?,?)
            ON CONFLICT(project,node_type,node_id) DO UPDATE SET
              title=CASE WHEN excluded.title <> '' THEN excluded.title ELSE trace_nodes.title END,
              metadata_json=CASE WHEN excluded.metadata_json <> '{}' THEN excluded.metadata_json ELSE trace_nodes.metadata_json END,
              updated_at=CURRENT_TIMESTAMP
            """,
            (project, node_type, node_id, title, _json(metadata)),
        )
    return {"ok": True, "project": project, "node": f"{node_type}:{node_id}"}


def record_edge(
    project: str,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relation: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record_node(project, source_type, source_id)
    record_node(project, target_type, target_id)
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO trace_edges(
              project,source_type,source_id,target_type,target_id,relation,metadata_json
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (project, source_type, source_id, target_type, target_id, relation, _json(metadata)),
        )
    return {
        "ok": True,
        "edge": f"{source_type}:{source_id} -[{relation}]-> {target_type}:{target_id}",
    }


def query_node(project: str, node_type: str, node_id: str) -> dict[str, Any]:
    with connect() as conn:
        node = conn.execute(
            "SELECT * FROM trace_nodes WHERE project=? AND node_type=? AND node_id=?",
            (project, node_type, node_id),
        ).fetchone()
        outgoing = conn.execute(
            "SELECT * FROM trace_edges WHERE project=? AND source_type=? AND source_id=? ORDER BY id",
            (project, node_type, node_id),
        ).fetchall()
        incoming = conn.execute(
            "SELECT * FROM trace_edges WHERE project=? AND target_type=? AND target_id=? ORDER BY id",
            (project, node_type, node_id),
        ).fetchall()
    return {
        "found": node is not None,
        "node": dict(node) if node else None,
        "outgoing": [dict(row) for row in outgoing],
        "incoming": [dict(row) for row in incoming],
    }


def find_path(project: str, source_type: str, source_id: str, target_type: str) -> dict[str, Any]:
    start = (source_type, source_id)
    queue: deque[tuple[tuple[str, str], list[tuple[str, str]]]] = deque([(start, [start])])
    seen = {start}
    with connect() as conn:
        while queue:
            (current_type, current_id), path = queue.popleft()
            if current_type == target_type and len(path) > 1:
                return {"found": True, "path": [{"type": t, "id": i} for t, i in path]}
            rows = conn.execute(
                "SELECT target_type,target_id FROM trace_edges WHERE project=? AND source_type=? AND source_id=?",
                (project, current_type, current_id),
            ).fetchall()
            for row in rows:
                nxt = (row["target_type"], row["target_id"])
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, path + [nxt]))
    return {"found": False, "path": []}


def requirement_coverage(project: str) -> dict[str, Any]:
    required_targets = ["task", "pr", "test", "release"]
    with connect() as conn:
        requirements = conn.execute(
            "SELECT node_id,title FROM trace_nodes WHERE project=? AND node_type='requirement' ORDER BY node_id",
            (project,),
        ).fetchall()
    details = []
    fully_covered = 0
    for req in requirements:
        coverage = {target: find_path(project, "requirement", req["node_id"], target)["found"] for target in required_targets}
        complete = all(coverage.values())
        fully_covered += int(complete)
        details.append({"requirement_id": req["node_id"], "title": req["title"], "coverage": coverage, "complete": complete})
    total = len(details)
    return {
        "project": project,
        "requirements": total,
        "fully_covered": fully_covered,
        "coverage_percent": round((fully_covered / total * 100), 2) if total else 0.0,
        "details": details,
    }
