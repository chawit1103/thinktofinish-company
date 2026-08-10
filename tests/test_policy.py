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


def test_kanban_handoff_is_autonomous():
    result = check_policy("review_required_handoff", "low")
    assert result["decision"] == "autonomous"
