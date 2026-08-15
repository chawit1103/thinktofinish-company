# ThinkToFinish Company Core

**Turn Hermes + Oh My Hermes into a governed AI Software Company.**

ThinkToFinish (TTF) is the **Company Governance layer** above Oh My Hermes (OMH) and Hermes Agent. It deliberately does not rebuild the agent runtime, generic work orchestration, memory engine, executor router, worktree manager, or Kanban scheduler.

```text
Owner / Chairman
      │
      ▼
ThinkToFinish Company Core
WHAT + WHY
Product Governance · Architecture Governance · Policy
Task Contracts · Traceability · Risk/Approval · Release · Metrics
      │
      ▼
Oh My Hermes (preferred Work Intelligence layer)
HOW TO ORGANIZE WORK
Interview · Research · Planning · Coordination · Coding-owner handoff
Long-horizon workflows · Project memory · Execution observation · Adversarial QA
      │
      ▼
Hermes Agent
HOW TO RUN IT
Profiles · Kanban · Goals/Loops · Native Review · Delegation
Sessions · Plugins · Gateway · Worktrees/Sandbox
      │
      ▼
Codex / Claude Code / pi / other coding owner
HOW TO IMPLEMENT IT
```

The core rule is:

> **ThinkToFinish owns WHAT and WHY. OMH owns HOW TO ORGANIZE THE WORK. Hermes owns HOW TO RUN IT. The selected coding owner owns HOW TO IMPLEMENT IT.**

This boundary is intentional. Hermes and OMH evolve quickly; upstream capability growth should normally let ThinkToFinish **delete execution glue**, not add more of it.

## What ThinkToFinish owns

- Business goal and scope authority
- Product Spec with stable requirement IDs and acceptance criteria
- Architecture Contract, ADRs, Decision Packet, security boundaries
- Company Task Contract / Definition of Done
- Autonomous / human-approval / forbidden policy
- Separation of duties and independent judgment
- Requirement → ADR → Task → Commit → PR → Test → Release traceability
- Integrated QA/Security company gate
- Release Evidence and Release Candidate decision
- Company metrics and governance learning

## What ThinkToFinish does not own

New projects must not depend on TTF implementations of:

- Kanban scheduling or graph dispatch internals
- generic Goal/Loop runtime
- generic memory runtime
- generic coding-executor routing
- worktree management
- Hermes session coordination
- ordinary implementation review/rework transitions
- direct mutation of Hermes `kanban.db`

The existing deterministic transition engine is retained only as a **legacy-board compatibility fallback** for boards created before Hermes gained the native review/rework lifecycle. It is disabled by default for new projects.

## Supported Work Layer

The current TTF-supported OMH baseline is pinned in `policies/runtime-boundary.json`:

```text
Oh My Hermes v1.0.6
commit 0106a636d7c971408e9caf634b5e21a471fc5082
channel stable
```

TTF does not follow OMH `main` automatically. The same rule applies to Hermes: runtime upgrades are compatibility-tested before being promoted.

## Quick Start

Prerequisites:

- Hermes Agent installed and configured
- Git
- Python 3.11+
- `curl` for the pinned OMH installer

Bootstrap the recommended stack:

```bash
./scripts/bootstrap-company.sh
```

This:

1. installs the pinned stable OMH baseline,
2. runs `omh setup` and `omh doctor`,
3. creates/updates the ThinkToFinish Hermes Profiles,
4. installs the portable TTF Company Core into those Profiles,
5. runs the lightweight layered compatibility check.

For a non-interactive or already-configured OMH host:

```bash
./scripts/bootstrap-company.sh --skip-omh-setup
```

To install only OMH:

```bash
./scripts/install-omh.sh
```

To inspect the local stack:

```bash
./scripts/doctor.sh
./scripts/compatibility-check.sh
```

## Company Roles

ThinkToFinish keeps company responsibility separate from generic workflow mechanics:

| Profile | Company authority |
|---|---|
| `orchestrator` | scope-aware company graph, routing, governance, closeout |
| `product` | authoritative Product Spec, requirement IDs, acceptance criteria |
| `architect` | authoritative ADRs/contracts/shared decisions/security boundaries |
| `engineer` | delivery against a Company Task Contract; may use OMH/coding owners |
| `qa-reviewer` | independent implementation review plus integrated QA/Security judgment |
| `release-manager` | release evidence, traceability, residual risk, RC readiness |

OMH workflows are **capabilities used by these roles**, not replacement company authorities. For example, `ulw-interview` can strengthen Product Discovery, but its output is not authoritative until the `product` role turns it into the TTF Product Spec.

## Review Model

New projects use **Hermes native same-card implementation review**:

```text
Engineer implements + verifies
        │
        ▼
kanban_request_review(reviewer="qa-reviewer")
        │
        ▼
Hermes REVIEW
   ┌────┴─────────┐
approve       request_changes
   │               │
 done          original implementer
                   │
                   └──────→ review again
```

Use `kanban_block` only for a genuine external stop such as human approval, production/destructive action, security exception, or a required unavailable capability.

Do **not** create a second pre-created review child for the same implementation phase while also using same-card review.

Separate downstream company gates remain first-class:

```text
Product Spec
    ↓
Architecture Contract + Decision Packet
    ↓
Engineering Work Packages
    ↓ native implementation review
Integration
    ↓ native implementation review
Integrated QA + Security
    ↓
Release Evidence
    ↓
Company Closeout / RC decision
```

OMH may organize work inside an Engineering Work Package, but the Hermes Kanban board should not mirror every OMH internal substep card-for-card.

## Evidence Standard

ThinkToFinish distinguishes prepared intent from observed evidence. A prepared plan, prepared coding handoff, green-looking status, or agent-reported completion does not prove execution or verification.

The Company Evidence Graph is:

```text
Requirement → ADR → Task → Commit → PR → Test → Release
```

A Release Candidate normally requires:

- acceptance criteria satisfied,
- CI/tests verified,
- independent review satisfied,
- integrated security evidence accepted,
- zero unresolved Critical/High findings under default policy,
- traceability complete,
- residual risks declared,
- release policy satisfied.

OMH QA success and Hermes task completion are useful evidence inputs, but neither alone is a TTF release decision.

## Pilot

Prepare a Git repository with at least one commit, then:

```bash
./scripts/create-pilot.sh ~/Projects/mini-hrms mini-hrms
```

Expected high-level graph:

```text
Product → Architecture → Engineering Work Packages
                         ↓
                    Integration
                         ↓
                   QA + Security
                         ↓
                  Release Evidence
                         ↓
                  Company Closeout
```

Implementation packages use native review loops internally rather than review-child/remediation graphs.

## Runtime Boundary

The machine-readable boundary is `policies/runtime-boundary.json`.

CI enforces that the portable `thinktofinish_company/` core does not import Hermes internals or address Hermes Kanban SQLite storage directly:

```bash
make boundary-check
```

The intent is to keep runtime-specific integration thin. When Hermes changes, compatibility impact should be isolated to adapters/integration surfaces rather than Company Core semantics.

## Legacy Transition Engine

`scripts/kanban-transition-engine.py` and its regression suite remain for migration support only.

Do not enable it on a newly-created board. Existing boards that still encode the old `blocked + ttf_review + remediation child` protocol can be migrated separately after confirming their review state and evidence lineage.

## Development

Run the repository tests:

```bash
make test
make boundary-check
make smoke
```

Static layered compatibility check:

```bash
./scripts/compatibility-check.sh --static
```

Installed-stack check:

```bash
./scripts/compatibility-check.sh
```

## Design Principle

```text
Hermes capability ↑
        ↓
TTF infrastructure code ↓
        ↓
TTF company intelligence ↑
```

ThinkToFinish should remain valuable even if the execution runtime changes. Hermes is the preferred execution OS and OMH the preferred work-intelligence layer, but Company Policy, Product/Architecture authority, traceability, risk/approval, and release governance remain TTF concerns.
