from __future__ import annotations

import json
from typing import Any

from .db import connect
from .safety import sanitize_metadata


def record_task_metric(
    project: str,
    task_id: str,
    status: str,
    cycle_seconds: float = 0,
    retries: int = 0,
    human_interventions: int = 0,
    cost_usd: float = 0,
    first_pass: bool = False,
    autonomous: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO task_metrics(
              project,task_id,status,cycle_seconds,retries,human_interventions,
              cost_usd,first_pass,autonomous,metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(project,task_id) DO UPDATE SET
              status=excluded.status,
              cycle_seconds=excluded.cycle_seconds,
              retries=excluded.retries,
              human_interventions=excluded.human_interventions,
              cost_usd=excluded.cost_usd,
              first_pass=excluded.first_pass,
              autonomous=excluded.autonomous,
              metadata_json=excluded.metadata_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                project,
                task_id,
                status,
                float(cycle_seconds),
                int(retries),
                int(human_interventions),
                float(cost_usd),
                int(bool(first_pass)),
                int(bool(autonomous)),
                json.dumps(sanitize_metadata(metadata or {}), ensure_ascii=False, sort_keys=True),
            ),
        )
    return {"ok": True, "project": project, "task_id": task_id}


def summary(project: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS tasks,
                   COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END),0) AS completed,
                   COALESCE(AVG(cycle_seconds),0) AS avg_cycle_seconds,
                   COALESCE(AVG(retries),0) AS avg_retries,
                   COALESCE(SUM(human_interventions),0) AS human_interventions,
                   COALESCE(SUM(cost_usd),0) AS cost_usd,
                   COALESCE(AVG(first_pass),0) AS first_pass_rate,
                   COALESCE(AVG(autonomous),0) AS autonomous_rate
            FROM task_metrics WHERE project=?
            """,
            (project,),
        ).fetchone()
    tasks = int(row["tasks"] or 0)
    return {
        "project": project,
        "tasks": tasks,
        "completed": int(row["completed"] or 0),
        "avg_cycle_seconds": round(float(row["avg_cycle_seconds"] or 0), 2),
        "avg_retries": round(float(row["avg_retries"] or 0), 2),
        "human_interventions": int(row["human_interventions"] or 0),
        "cost_usd": round(float(row["cost_usd"] or 0), 4),
        "first_pass_rate_percent": round(float(row["first_pass_rate"] or 0) * 100, 2),
        "autonomous_completion_rate_percent": round(float(row["autonomous_rate"] or 0) * 100, 2),
    }
