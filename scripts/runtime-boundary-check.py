#!/usr/bin/env python3
"""Static checks for the ThinkToFinish Company-Core runtime boundary."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "policies" / "runtime-boundary.json"
CORE = ROOT / "thinktofinish_company"

BANNED_CORE_PATTERNS = {
    r"\bimport\s+hermes_cli\b": "Company Core must not import Hermes internal modules",
    r"\bfrom\s+hermes_cli\b": "Company Core must not import Hermes internal modules",
    r"kanban_db": "Company Core must not depend on Hermes kanban_db internals",
    r"\.hermes[/\\]kanban": "Company Core must not address Hermes Kanban storage directly",
    r"kanban\.db": "Company Core must not mutate Hermes Kanban SQLite directly",
}


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["schema"] == "ttf_runtime_boundary/v1"
    assert policy["work_layer"]["preferred"] == "oh-my-hermes"
    assert re.fullmatch(r"[0-9a-f]{40}", policy["work_layer"]["commit"])
    assert policy["work_layer"]["follow_main"] is False
    assert policy["execution_runtime"]["follow_main"] is False
    assert policy["legacy"]["kanban_transition_engine"]["enabled_by_default"] is False
    assert policy["legacy"]["kanban_transition_engine"]["new_projects_must_not_depend_on_it"] is True

    violations: list[str] = []
    for path in sorted(CORE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern, reason in BANNED_CORE_PATTERNS.items():
            if re.search(pattern, text):
                violations.append(f"{path.relative_to(ROOT)}: {reason} ({pattern})")
    if violations:
        raise SystemExit("Runtime boundary violations:\n- " + "\n- ".join(violations))

    print(
        "RUNTIME_BOUNDARY_OK "
        f"omh={policy['work_layer']['version']}@{policy['work_layer']['commit'][:12]} "
        "legacy_transition_engine=off"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
