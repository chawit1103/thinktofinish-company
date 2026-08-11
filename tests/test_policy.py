import pytest

from thinktofinish_company import policy
from thinktofinish_company.policy import check_policy


def test_autonomous_action():
    result = check_policy("coding", "medium")
    assert result["decision"] == "autonomous"
    assert result["allowed"] is True


def test_high_risk_upgrades_autonomous_to_human():
    result = check_policy("coding", "high")
    assert result["decision"] == "human_approval"


def test_production_is_human_gated():
    result = check_policy("production_deployment", "medium")
    assert result["decision"] == "human_approval"


def test_forbidden_action():
    result = check_policy("direct_push_main", "low")
    assert result["decision"] == "forbidden"
    assert result["allowed"] is False


def test_review_request_changes_is_autonomous():
    result = check_policy("review_request_changes", "low")
    assert result["decision"] == "autonomous"


def test_review_required_handoff_is_autonomous():
    result = check_policy("review_required_handoff", "low")
    assert result["decision"] == "autonomous"
    assert result["requires_human"] is False


@pytest.mark.parametrize("action", ["review_required_handoff", "review_request_changes"])
@pytest.mark.parametrize("risk", ["high", "critical"])
def test_never_block_transitions_stay_autonomous_at_elevated_risk(action, risk):
    result = check_policy(action, risk)
    assert result["decision"] == "autonomous"
    assert result["requires_human"] is False
    assert result["allowed"] is True


def test_security_policy_still_overrides_never_block(monkeypatch):
    action = "review_request_changes"
    security = {"protected_actions": [action], "forbidden_actions": []}

    def fake_load(path):
        if path == "policies/kanban-autopilot.yaml":
            return {"actions": {action: "autonomous"}, "never_block_for": [action]}
        if path == "policies/security.yaml":
            return security
        return {"default": "human_approval", "actions": {}}

    monkeypatch.setattr(policy, "load_yaml", fake_load)
    assert policy.check_policy(action, "high")["decision"] == "human_approval"
    security["forbidden_actions"] = [action]
    assert policy.check_policy(action, "high")["decision"] == "forbidden"
