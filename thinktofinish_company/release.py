from __future__ import annotations

from typing import Any

from .config import load_yaml


def check_release_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    quality = load_yaml("policies/quality.yaml")
    security_policy = load_yaml("policies/security.yaml")
    errors: list[str] = []
    warnings: list[str] = []

    required_top = quality.get("release_evidence_required", [])
    for key in required_top:
        if key not in evidence:
            errors.append(f"Missing release evidence: {key}")

    ci = evidence.get("ci", {})
    if not isinstance(ci, dict) or ci.get("status") != "pass":
        errors.append("CI must have status=pass")

    tests = evidence.get("tests", {})
    if not isinstance(tests, dict) or tests.get("status") != "pass":
        errors.append("Tests must have status=pass")

    review = evidence.get("review", {})
    if quality.get("independent_review_required", True):
        if not isinstance(review, dict) or review.get("status") != "approved":
            errors.append("Independent review must be approved")

    security = evidence.get("security", {})
    if quality.get("security_review_required", True):
        if not isinstance(security, dict) or security.get("status") != "pass":
            errors.append("Security review must have status=pass")
        critical = int(security.get("critical_findings", 0) or 0) if isinstance(security, dict) else 0
        high = int(security.get("high_findings", 0) or 0) if isinstance(security, dict) else 0
        if critical > int(security_policy.get("max_critical_findings", 0)):
            errors.append("Critical security findings exceed policy")
        if high > int(security_policy.get("max_high_findings", 0)):
            errors.append("High security findings exceed policy")

    if not evidence.get("traceability_complete", False):
        errors.append("Requirement traceability is incomplete")

    residual = evidence.get("residual_risks", [])
    if residual:
        warnings.append(f"Residual risks declared: {len(residual)}")

    approvals = evidence.get("approvals", {})
    if evidence.get("target_environment") == "production":
        if not isinstance(approvals, dict) or not approvals.get("production_deployment", False):
            errors.append("Production deployment requires human approval")

    return {
        "pass": not errors,
        "decision": "release_candidate_ready" if not errors else "blocked",
        "errors": errors,
        "warnings": warnings,
        "release": evidence.get("release"),
        "project": evidence.get("project"),
    }
