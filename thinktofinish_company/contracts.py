from __future__ import annotations

from typing import Any


REQUIRED_FIELDS = {
    "id": str,
    "title": str,
    "goal": str,
    "inputs": list,
    "outputs": list,
    "acceptance_criteria": list,
    "verification": list,
    "risk": str,
    "assignee_role": str,
}

RISK_LEVELS = {"low", "medium", "high", "critical"}


def validate_task_contract(contract: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(contract, dict):
        return {"valid": False, "errors": ["Contract must be an object."], "warnings": []}

    for key, expected in REQUIRED_FIELDS.items():
        if key not in contract:
            errors.append(f"Missing required field: {key}")
            continue
        if not isinstance(contract[key], expected):
            errors.append(f"Field {key} must be {expected.__name__}")

    for key in ("title", "goal", "assignee_role"):
        if isinstance(contract.get(key), str) and not contract[key].strip():
            errors.append(f"Field {key} cannot be empty")

    for key in ("inputs", "outputs", "acceptance_criteria", "verification"):
        value = contract.get(key)
        if isinstance(value, list):
            if not value:
                errors.append(f"Field {key} must contain at least one item")
            elif any(not isinstance(item, str) or not item.strip() for item in value):
                errors.append(f"Field {key} must contain non-empty strings")

    risk = str(contract.get("risk", "")).lower()
    if risk and risk not in RISK_LEVELS:
        errors.append(f"risk must be one of {sorted(RISK_LEVELS)}")

    review = contract.get("review")
    if review is None:
        warnings.append("review section missing; independent review should be explicit")
    elif not isinstance(review, dict):
        errors.append("review must be an object")

    security = contract.get("security")
    if security is None:
        warnings.append("security section missing; security review should be explicit")
    elif not isinstance(security, dict):
        errors.append("security must be an object")

    traceability = contract.get("traceability")
    if traceability is None:
        warnings.append("traceability section missing")
    elif not isinstance(traceability, dict):
        errors.append("traceability must be an object")
    else:
        ids = traceability.get("requirement_ids", [])
        if ids and (not isinstance(ids, list) or any(not isinstance(x, str) for x in ids)):
            errors.append("traceability.requirement_ids must be a list of strings")

    if risk in {"high", "critical"}:
        if not isinstance(review, dict) or not review.get("required", False):
            errors.append("high/critical risk tasks require independent review")
        if not isinstance(security, dict) or not security.get("required", False):
            errors.append("high/critical risk tasks require security review")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "contract_id": contract.get("id"),
    }
