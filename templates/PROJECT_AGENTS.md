# ThinkToFinish Project Constitution

This project is operated by the ThinkToFinish AI Software Company model on Hermes.

## Operating Model

- Agent = Capability
- Loop = Reliability
- Graph = Organization
- Governance = Company
- One Hermes Kanban Board = one project
- Kanban = macro workflow; each worker uses a bounded internal repair/verification loop

`goal_mode` is for a card that can satisfy its own acceptance criteria. A code producer with an independent reviewer child must not use it: a verified `review-required:` handoff completes the producer and dispatches the reviewer.

## Delivery Rules

1. Every meaningful implementation task must have explicit acceptance criteria and deterministic verification.
2. Stable requirement IDs must exist before implementation is considered complete.
3. Producer and independent reviewer are separate roles.
4. Engineering changes use branches/worktrees and PRs; never push directly to `main`.
5. Do not bypass failing tests, required review, security controls, or traceability.
6. Never place secrets in task bodies, comments, traceability metadata, release evidence, logs, or commits.
7. Human approval is required for production deployment, destructive DB migrations, credential changes, paid-service purchases, major scope changes, production DB writes, and security exceptions.
8. Direct push to main, bypassing required review, disabling security controls, and exposing credentials are forbidden.
9. Autonomous work ends at Release Candidate unless an explicit production approval gate is satisfied.
10. Preserve existing project-specific conventions and tighter security rules; this document is a floor, not permission to weaken them.
11. Reserve retained `blocked` states for a human gate, a hard safety boundary, or a truly unavailable capability. An untyped review block may briefly trigger deterministic remediation; review waiting, dependencies, and ordinary technical decisions advance automatically.

## Required Evidence

Prefer a traceability chain such as:

`Requirement → Task → Commit → PR → Test → Release`

Kanban completion metadata should state:
- changed files or produced artifacts
- verification commands/results
- dependencies/handoffs
- retry notes when applicable
- residual risks / untested areas

## Definition of Done

A feature is not done because an agent says “done.” It is done when its acceptance criteria and deterministic verification pass, independent review is satisfied where required, and its delivery evidence is traceable.
