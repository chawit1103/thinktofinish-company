---
name: company-orchestrator
description: Govern software delivery above OMH work intelligence and Hermes execution.
version: 0.3.0
author: ThinkToFinish
license: MIT
compatibility: Hermes Agent with ThinkToFinish Company MCP tools; Oh My Hermes recommended.
metadata:
  category: governance
  layer: company
---
# Company Orchestrator

## When to Use
Use when a user gives a product/software outcome rather than a single implementation task, for example "build a mini HRMS" or "ship feature X end to end".

## Layer Contract

- **ThinkToFinish = WHAT + WHY**: company scope, authoritative Product/Architecture artifacts, Task Contracts, policy, traceability, QA/Security judgment, release governance, metrics.
- **Oh My Hermes = HOW TO ORGANIZE WORK** when available: interview, research, planning, coordination, coding-owner handoff, long-horizon work, project memory, execution observation, adversarial QA.
- **Hermes = HOW TO RUN IT**: Profiles, Kanban, Goals/Loops, native review/rework, delegation, sessions, plugins, gateway, worktrees/sandbox.
- **Coding owner = HOW TO IMPLEMENT IT**.

## Procedure
1. Identify the project/board. One independent software project should normally use one Hermes Kanban board.
2. Create only the company-sized macro phases needed for the outcome; do not build a parallel scheduler or mirror every OMH substep in Kanban.
3. Product and Architecture phases may call OMH capabilities, but their authoritative outputs remain TTF Product Spec / Architecture Contract.
4. Before high-value implementation, require a Company Task Contract and call `ttf_validate_task_contract`.
5. Route implementation to `engineer`; OMH may organize or prepare an explicit coding-owner handoff within that work package.
6. Use Hermes native same-card implementation review with a separate reviewer identity. Do not pre-create another review child for the same phase.
7. Keep integrated QA/Security and Release Evidence as separate downstream company gates.
8. Record traceability as real artifacts appear: requirement → ADR → task → commit → PR → test → release.
9. Call `ttf_policy_check` before risky actions; stop for `human_approval` and never perform `forbidden` actions.
10. Call `ttf_release_gate` before declaring a Release Candidate ready and record terminal company metrics.

## Rules
- Prefer 2–6 meaningful company work packages, not dozens of micro-cards.
- Parallelize only genuinely independent work and stabilize shared decisions first.
- Prepared plans/handoffs are not observed execution evidence.
- `kanban_block` is for a real human/safety/capability stop, not review waiting or ordinary rework.
- The legacy TTF transition engine is not a normal path for new projects.
- Never expose secrets in Kanban/traceability/release metadata.
- Production, destructive migrations, credentials, paid purchases, major scope changes, production DB writes, and security exceptions are human-gated by policy.

## Completion Standard
A project is not complete because implementation cards or OMH workflows are green. It is complete at the requested company boundary only when acceptance criteria, deterministic evidence, independent judgment, security evidence, traceability, residual risk, and release policy are satisfied.
