from pathlib import Path

from thinktofinish_company.metrics import record_task_metric
from thinktofinish_company.traceability import query_node, record_node


def test_traceability_redacts_secret_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TTF_COMPANY_DATA", str(tmp_path))
    record_node("p", "task", "T1", "Task", {"api_key": "sk-abcdefghijklmnop", "safe": "ok"})
    node = query_node("p", "task", "T1")["node"]
    assert "sk-abcdefghijklmnop" not in node["metadata_json"]
    assert "[REDACTED]" in node["metadata_json"]
    assert '"safe": "ok"' in node["metadata_json"]


def test_metric_metadata_redacts_token_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TTF_COMPANY_DATA", str(tmp_path))
    record_task_metric("p", "T1", "done", metadata={"access_token": "raw-value"})
    import sqlite3
    db = sqlite3.connect(tmp_path / "company.db")
    try:
        value = db.execute("select metadata_json from task_metrics where project='p' and task_id='T1'").fetchone()[0]
    finally:
        db.close()
    assert "raw-value" not in value
    assert "[REDACTED]" in value
