# ThinkToFinish Project Constitution

This project is operated using the layered ThinkToFinish model:

```text
ThinkToFinish Company Core → Oh My Hermes Work Intelligence → Hermes Execution OS → Coding Owner
```

## Authority

- ThinkToFinish owns WHAT/WHY: business scope, Product Spec, requirement IDs, Architecture Contract/ADRs, Company Task Contracts, company policy, traceability, risk/approval, QA/Security judgment, release governance, and company metrics.
- Oh My Hermes may own HOW TO ORGANIZE WORK: interview, research, planning, work coordination, coding-owner handoff, project memory, and execution observation.
- Hermes owns HOW TO RUN IT: Profiles, Kanban, Goals/Loops, native review/rework, delegation, sessions, plugins, gateway, and worktree/sandbox runtime.
- The selected coding owner owns HOW TO IMPLEMENT IT.

A lower layer may supply evidence or capability but must not silently acquire higher-layer company authority.

## Delivery Rules

1. Every meaningful implementation task has explicit acceptance criteria and deterministic verification in a Company Task Contract.
2. Stable requirement IDs exist before implementation is considered complete.
3. Shared architectural decisions are stabilized before wide parallel fan-out.
4. Producer and independent reviewer are separate identities.
5. Same-card implementation review uses Hermes native `kanban_request_review` / `kanban_request_changes`; do not create a duplicate pre-created reviewer child for the same phase.
6. `kanban_block` is reserved for genuine human/safety/capability stops, not review waiting or ordinary rework.
7. OMH may organize work, but do not mirror its internal sub-work card-for-card into the company Kanban graph.
8. Engineering changes use effective isolation appropriate to risk and PRs; never push directly to `main`.
9. Do not bypass failing tests, required review, security controls, traceability, or company release policy.
10. Never place secrets in task bodies, comments, traceability metadata, release evidence, logs, or commits.
11. Human approval is required for production deployment, destructive DB migrations, credential changes, paid-service purchases, major scope changes, production DB writes, and security exceptions.
12. Autonomous company delivery ends at Release Candidate unless an explicit production approval gate is satisfied.
13. Preserve existing project-specific conventions and tighter security rules; this constitution is a floor, not permission to weaken them.

## Evidence Boundary

Prepared intent is not observed execution evidence.

Prefer the company traceability chain:

`Requirement → ADR → Task → Commit → PR → Test → Release`

OMH plan/handoff, Hermes task status, coding-owner report, review result, CI receipt, and release decision must be represented at the actual evidence strength observed.

## Definition of Done

A feature is not done because an agent says "done". It is done at the relevant company boundary when acceptance criteria and deterministic verification pass, independent judgment is satisfied where required, security evidence is acceptable, traceability is sufficient, residual risk is declared, and release policy permits the claim.
