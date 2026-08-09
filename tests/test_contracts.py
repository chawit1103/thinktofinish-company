from thinktofinish_company.contracts import validate_task_contract


def base_contract():
    return {
        "id": "T-1",
        "title": "Implement RBAC",
        "goal": "Enforce permissions",
        "inputs": ["PRD"],
        "outputs": ["code", "tests"],
        "acceptance_criteria": ["403 when unauthorized"],
        "verification": ["pytest -q"],
        "risk": "medium",
        "assignee_role": "engineer",
        "review": {"required": True, "profile": "qa-reviewer"},
        "security": {"required": True, "profile": "qa-reviewer"},
        "traceability": {"requirement_ids": ["REQ-1"]},
    }


def test_valid_contract():
    assert validate_task_contract(base_contract())["valid"] is True


def test_missing_field_invalid():
    contract = base_contract()
    del contract["verification"]
    result = validate_task_contract(contract)
    assert result["valid"] is False
    assert any("verification" in e for e in result["errors"])


def test_high_risk_requires_review_security():
    contract = base_contract()
    contract["risk"] = "high"
    contract["review"] = {"required": False}
    contract["security"] = {"required": False}
    result = validate_task_contract(contract)
    assert result["valid"] is False
    assert len(result["errors"]) >= 2
