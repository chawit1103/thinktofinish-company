import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]


def runtime_policy():
    return json.loads((ROOT / "policies" / "runtime-boundary.json").read_text(encoding="utf-8"))


def test_runtime_boundary_pins_work_layer_and_disables_legacy_engine():
    policy = runtime_policy()
    assert policy["schema"] == "ttf_runtime_boundary/v1"
    assert policy["work_layer"]["preferred"] == "oh-my-hermes"
    assert policy["work_layer"]["version"] == "1.0.6"
    assert re.fullmatch(r"[0-9a-f]{40}", policy["work_layer"]["commit"])
    assert policy["work_layer"]["follow_main"] is False
    assert policy["execution_runtime"]["follow_main"] is False
    assert policy["legacy"]["kanban_transition_engine"]["enabled_by_default"] is False
    assert policy["legacy"]["kanban_transition_engine"]["new_projects_must_not_depend_on_it"] is True


def test_company_core_does_not_import_hermes_internals_or_kanban_db():
    patterns = [
        r"\bimport\s+hermes_cli\b",
        r"\bfrom\s+hermes_cli\b",
        r"kanban_db",
        r"\.hermes[/\\]kanban",
        r"kanban\.db",
    ]
    for path in sorted((ROOT / "thinktofinish_company").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not re.search(pattern, text), f"{path}: runtime boundary violation: {pattern}"


def test_default_pilot_uses_native_same_card_review_not_legacy_handoff():
    text = (ROOT / "scripts" / "create-pilot.sh").read_text(encoding="utf-8")
    assert "kanban_request_review" in text
    assert "kanban_request_changes" in text
    assert "same-card" in text
    assert "Do NOT create a pre-created review child" in text
    assert "review-required:" not in text
    assert "legacy TTF transition engine" in text


def test_omh_installer_is_source_pinned_not_main():
    policy = runtime_policy()
    script = (ROOT / "scripts" / "install-omh.sh").read_text(encoding="utf-8")
    assert policy["work_layer"]["commit"] in script
    assert policy["work_layer"]["version"] in script
    assert "raw.githubusercontent.com/rlaope/oh-my-hermes/${OMH_COMMIT}/install.sh" in script
    assert "oh-my-hermes/main/install.sh" not in script
