import os
from pathlib import Path

from thinktofinish_company.traceability import (
    find_path,
    record_edge,
    record_node,
    requirement_coverage,
)


def test_traceability_path_and_coverage(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TTF_COMPANY_DATA", str(tmp_path))
    p = "pilot"
    record_node(p, "requirement", "REQ-1", "Login")
    record_edge(p, "requirement", "REQ-1", "task", "T-1", "implemented_by")
    record_edge(p, "task", "T-1", "pr", "PR-1", "delivered_by")
    record_edge(p, "pr", "PR-1", "test", "TEST-1", "verified_by")
    record_edge(p, "test", "TEST-1", "release", "v0.1", "included_in")

    assert find_path(p, "requirement", "REQ-1", "release")["found"] is True
    coverage = requirement_coverage(p)
    assert coverage["coverage_percent"] == 100.0


def test_record_edge_does_not_erase_existing_node_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TTF_COMPANY_DATA", str(tmp_path))
    from thinktofinish_company.traceability import query_node

    p = "preserve"
    record_node(p, "requirement", "REQ-9", "Important requirement", {"owner": "product"})
    record_edge(p, "requirement", "REQ-9", "task", "T-9", "implemented_by")
    node = query_node(p, "requirement", "REQ-9")["node"]
    assert node["title"] == "Important requirement"
    assert '"owner": "product"' in node["metadata_json"]
