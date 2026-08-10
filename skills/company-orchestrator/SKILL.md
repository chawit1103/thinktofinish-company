---
name: company-orchestrator
description: Orchestrate software delivery with Hermes Kanban using Company Policy, Task Contracts, evidence, and human gates.
license: MIT
compatibility: Hermes Agent with Kanban and ThinkToFinish Company MCP tools enabled.
metadata:
  category: orchestration
  layer: company
---
# Company Orchestrator

## When to Use
Use when a user gives a product or software outcome rather than a single implementation task, for example "build a mini HRMS" or "ship feature X end to end".

## Operating Model
Treat Hermes as the execution OS and this skill as company governance.

- **Agent = Capability**: route work to the best profile.
- **Loop = Reliability**: use goal-mode cards for work that must iterate until explicit acceptance criteria are met.
- **Graph = Organization**: use Kanban dependencies for macro workflow and parallelism.
- **Governance = Company**: call `ttf_policy_check`, validate contracts, preserve traceability, and enforce release evidence.

## Procedure
1. Identify the project/board. One independent software project should use one Hermes Kanban board.
2. Convert the user's goal into a small product-delivery graph. Prefer native Triage Auto Decompose when appropriate; do not build a parallel scheduler.
3. Before creating high-value implementation cards, express each as a Company Task Contract and call `ttf_validate_task_contract`.
4. Route technical work to profiles by capability. The orchestrator should coordinate, not implement production code.
5. Use `goal_mode=True` only for an orchestration/research card whose completion does not depend on a downstream child. Code producers that hand off to an independent review use normal cards: their terminal outcome is a verified commit handoff.
6. Use worktree workspaces for coding tasks. Require PR/CI for integration.
7. Record traceability as artifacts appear: requirement → task → commit → PR → test → release.
8. Run independent review and security review before release evidence is accepted.
9. Before any risky action call `ttf_policy_check`. Stop for human approval when the result is `human_approval`; never perform `forbidden` actions.
10. Call `ttf_release_gate` before declaring a release candidate ready.
11. Record metrics at terminal task outcomes so the company can learn across projects.

## Orchestration Rules
- Prefer 2-6 meaningful tasks per decomposition; avoid dozens of tiny cards.
- Parallelize only genuinely independent work.
- Downstream cards must receive structured handoff evidence, not "done" prose.
- A producer cannot be the only judge of its own output.
- Pre-create a read-only reviewer child for every code producer. A `review-required:` handoff completes the producer and promotes that child; never mark review waiting as `blocked`.
- A reviewer `REQUEST_CHANGES` creates one remediation producer and its reviewer child automatically. Preserve failed cards as evidence; do not require an operator to repair ordinary graph transitions.
- Reserve `blocked` for a retained human gate, a real safety boundary, or an unavailable required capability after safe alternatives. Dependency waits and routine tool approval timeouts are not human-input blocks.
- Do not expose secrets in Kanban metadata or traceability metadata.
- Business scope, production deployment, destructive migrations, paid purchases, credentials, and security exceptions are human-gated by policy.

## Completion Standard
A project is not complete because implementation cards are green. It is complete when required acceptance criteria, CI, independent review, security evidence, traceability, and release policy are all satisfied.
