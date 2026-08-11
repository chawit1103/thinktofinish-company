from __future__ import annotations

from typing import Any

from .config import load_yaml


VALID_DECISIONS = {"autonomous", "human_approval", "forbidden"}


def check_policy(action: str, risk: str = "medium", context: str = "") -> dict[str, Any]:
    autonomy = load_yaml("policies/autonomy.yaml")
    kanban = load_yaml("policies/kanban-autopilot.yaml")
    security = load_yaml("policies/security.yaml")

    normalized = action.strip().lower().replace(" ", "_")
    actions = {**autonomy.get("actions", {}), **kanban.get("actions", {})}
    decision = actions.get(normalized, autonomy.get("default", "human_approval"))
    if decision not in VALID_DECISIONS:
        decision = "human_approval"

    reasons: list[str] = []
    if normalized not in actions:
        reasons.append("Action is not explicitly classified; conservative default applied.")

    risk_level = risk.strip().lower()
    never_block = set(kanban.get("never_block_for", []))
    if risk_level in {"high", "critical"} and decision == "autonomous" and normalized not in never_block:
        decision = "human_approval"
        reasons.append("High/critical risk upgrades autonomous action to human approval.")

    forbidden = set(security.get("forbidden_actions", []))
    if normalized in forbidden:
        decision = "forbidden"
        reasons.append("Security policy explicitly forbids this action.")

    protected = set(security.get("protected_actions", []))
    if normalized in protected and decision == "autonomous":
        decision = "human_approval"
        reasons.append("Security policy requires a human gate for this protected action.")

    if not reasons:
        reasons.append(f"Action classified as {decision} by autonomy policy.")

    return {
        "action": normalized,
        "risk": risk_level,
        "decision": decision,
        "requires_human": decision == "human_approval",
        "allowed": decision != "forbidden",
        "reasons": reasons,
        "context": context,
    }
