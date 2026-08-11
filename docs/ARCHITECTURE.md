# Architecture — Agent + Loop + Graph + Governance

## Boundary

ThinkToFinish Company Layer intentionally sits **above** Hermes. It does not own execution scheduling.

```text
┌────────────────────────────────────────────────────────────┐
│ Owner / Chairman                                           │
│ business goal · scope · high-risk approvals                │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│ ThinkToFinish Company Layer                                │
│ Policy · Task Contract · Traceability · Release · Metrics  │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│ Hermes Execution OS                                        │
│ Profiles · Kanban · Goal Loop · Worktrees · Skills · CI    │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
                      Project artifacts
```

## Agent

Persistent Hermes Profiles are company roles. Each has a role charter in `SOUL.md` plus access to the portable Company Layer.

```text
orchestrator    → decomposition, routing, replanning, closeout
product         → requirements and Product Spec
architect       → ADRs, contracts, technical boundaries
engineer        → implementation and deterministic verification
qa-reviewer     → independent judgment and security review
release-manager → evidence aggregation and release readiness
```

## Loop

A meaningful engineering card is a micro loop:

```text
Task Contract
     ↓
 Implement
     ↓
 deterministic gate
   ┌─┴─────────┐
 PASS         FAIL
   │            ↓
   │         diagnose
   │            ↓
   │          repair
   │            └──────→ gate
   ▼
 handoff evidence
```

Use the worker's internal repair loop for code producers, then complete a normal card into an independent reviewer child. Reserve Hermes goal-mode for self-contained orchestration/research cards whose completion does not depend on that downstream review.

## Graph

Kanban is the macro workflow. Dependencies are durable edges; independent cards may run in parallel.

The V0.1 pilot deliberately stages graph creation:

```text
Kickoff Orchestrator
        │
        ▼
Product Spec
        │
        ▼
Architecture
        │
        ▼
Engineering Graph Planner (Orchestrator)
   ┌────────┼───────────┐
   ▼        ▼           ▼
 BE/API   FE/UI      Data/Auth
   ▼        ▼           ▼
 Review   Review      Review
   └────────┼───────────┘
            ▼
       Integration
            ▼
    Integration Review
            ▼
       QA + Security
        ▼
 Release Evidence
        ▼
 Company Closeout
```

The second orchestrator wakes **after architecture** so it can create implementation cards from real contracts instead of guessing them at project intake.

## Governance

Every important action is one of:

```text
autonomous      → proceed within contract
a human approval → block/escalate until explicit decision
forbidden        → do not execute
```

Task Contracts define what “done” means. Traceability proves why each artifact exists. Release Evidence determines whether delivery is ready. Metrics tell whether autonomy is improving without sacrificing quality.

## Evidence Graph

```text
Requirement → ADR → Task → Commit → PR → Test → Release
```

V0.1 coverage requires each requirement to have a path to Task, PR, Test, and Release.

## Security boundary

Profiles are not filesystem sandboxes. Security relies on:

- least-privilege role credentials
- isolated worktrees / sandboxed terminal runtime where appropriate
- no production credentials for engineering workers
- human gates for production/destructive/security-exception actions
- independent review
- explicit release evidence
- metadata secret-redaction as defense in depth

## Why portable-first

Portable Agent Plugin components give the Company Layer reusable skills and MCP tools without patching Hermes core. Native Hermes hooks should be added only when a measured gap requires automatic lifecycle ingestion or privileged deterministic enforcement.
