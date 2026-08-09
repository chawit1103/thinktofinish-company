from pathlib import Path

from thinktofinish_company.metrics import record_task_metric, summary
from thinktofinish_company.release import check_release_evidence


def evidence():
    return {
        "project": "pilot",
        "release": "v0.1.0-rc1",
        "target_environment": "staging",
        "ci": {"status": "pass"},
        "tests": {"status": "pass"},
        "review": {"status": "approved"},
        "security": {"status": "pass", "critical_findings": 0, "high_findings": 0},
        "traceability_complete": True,
        "residual_risks": [],
        "approvals": {"production_deployment": False},
    }


def test_release_gate_passes_for_staging():
    assert check_release_evidence(evidence())["pass"] is True


def test_production_requires_human_approval():
    e = evidence()
    e["target_environment"] = "production"
    result = check_release_evidence(e)
    assert result["pass"] is False
    assert any("human approval" in x.lower() for x in result["errors"])


def test_metrics_summary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TTF_COMPANY_DATA", str(tmp_path))
    record_task_metric("pilot", "T1", "done", 100, 0, 0, 0.10, True, True)
    record_task_metric("pilot", "T2", "done", 200, 1, 1, 0.20, False, False)
    data = summary("pilot")
    assert data["tasks"] == 2
    assert data["completed"] == 2
    assert data["autonomous_completion_rate_percent"] == 50.0
    assert data["first_pass_rate_percent"] == 50.0


def test_metrics_are_upserted_per_task(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TTF_COMPANY_DATA", str(tmp_path))
    record_task_metric("pilot-upsert", "T1", "running", 10, 0, 0, 0.01, False, True)
    record_task_metric("pilot-upsert", "T1", "done", 30, 1, 0, 0.03, False, True)
    data = summary("pilot-upsert")
    assert data["tasks"] == 1
    assert data["completed"] == 1
    assert data["avg_cycle_seconds"] == 30.0
    assert data["avg_retries"] == 1.0
