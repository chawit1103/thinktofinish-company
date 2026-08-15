# Oh My Hermes Integration

## Purpose

Oh My Hermes (OMH) is the preferred **Work Intelligence layer** between ThinkToFinish Company Governance and Hermes Agent execution.

TTF does not treat OMH as the company authority and does not mirror OMH's internal workflow state into a second orchestration graph. OMH is a reusable capability layer for interview, research, planning, coordination, coding-owner handoff, memory, execution observation, and adversarial QA.

## Supported Baseline

The supported pin is stored in `policies/runtime-boundary.json`:

```text
version: 1.0.6
release commit: 0106a636d7c971408e9caf634b5e21a471fc5082
channel: stable
follow_main: false
```

The pinned release wheel published for v1.0.6 has SHA-256:

```text
30daee80ab091e1de2af30b290b4e4f089eaa813d7e9a243bac151aae3a3b888
```

The TTF installer retrieves `install.sh` from the exact release commit, not from `main`.

## Installation

Recommended one-command company bootstrap:

```bash
./scripts/bootstrap-company.sh
```

OMH only:

```bash
./scripts/install-omh.sh
```

Useful options:

```bash
./scripts/install-omh.sh --skip-setup
./scripts/install-omh.sh --smoke
./scripts/bootstrap-company.sh --skip-omh-setup
./scripts/bootstrap-company.sh --omh-smoke
```

`omh setup` can contain interactive configuration decisions, especially around model aliases. Review such changes rather than silently replacing existing local model/provider choices.

## Authority Rules

### Product Discovery

Allowed:

```text
TTF Product role
   ├─ OMH ulw-interview
   └─ OMH ulw-research
         ↓
TTF Product Spec
```

Not allowed:

```text
OMH interview/plan output
         ↓
automatically authoritative Product Spec
```

### Architecture

OMH can research options and improve planning. The TTF architect still owns accepted ADRs, shared contracts, the Decision Packet, security boundaries, and verification plan.

### Engineering

The Company Task Contract is an invariant input. OMH may organize work or select/prepare coding-owner handoffs, but may not weaken acceptance criteria, required verification, security requirements, or human gates to fit an executor.

Do not duplicate OMH work units as Hermes Kanban cards unless they represent independent company deliverables with real dependency/ownership value.

### Review

Implementation review is Hermes native same-card review. OMH may supply review/QA evidence, but ordinary `changes_requested` uses Hermes native `kanban_request_changes` rather than a TTF remediation graph.

### QA and Release

OMH `ulw-qa` output is an evidence source, not release authority.

```text
OMH QA evidence
      ↓
TTF independent QA/Security judgment
      ↓
TTF Release Evidence
      ↓
TTF Release Gate
```

## Prepared vs Observed

TTF adopts the strict evidence boundary that a prepared handoff or plan is not proof that a coding owner executed it.

Examples:

- prepared coding prompt ≠ code changed,
- dispatched/started ≠ completed,
- agent says tests pass ≠ test receipt observed,
- plan approved ≠ release approved,
- OMH QA card ready ≠ TTF QA/Security passed.

Only record evidence at the strength actually observed.

## Memory

TTF should not build a competing generic project-memory engine. OMH may own work/project memory lifecycle. TTF stores only company-governance facts necessary for policy, traceability, release evidence, and metrics.

Examples appropriate for TTF storage:

- stable requirement ID and approved scope,
- ADR identifier,
- policy/approval receipt reference,
- task/commit/PR/test/release trace nodes,
- residual risk decision,
- terminal company metric.

Raw conversations, executor logs, hidden reasoning, and generic project recollections do not belong in the TTF evidence database by default.

## Failure and Fallback

OMH is preferred but not Company Core authority. If OMH is unavailable:

- TTF Product/Architecture/Policy/Traceability/Release contracts remain valid,
- Hermes-native capabilities may be used directly,
- do not silently weaken evidence/review/security requirements,
- record capability unavailability where it affects delivery confidence.

This means OMH can be upgraded or temporarily removed without changing the meaning of a TTF release decision.

## Upgrade Process

Do not run `omh update` directly on a managed Company runtime and automatically accept the result as supported.

Recommended process:

1. Discover the new stable OMH release.
2. Resolve its exact release commit.
3. Review release notes for routing, evidence, approval, worktree, memory, review, and coding-owner semantic changes.
4. Update the pin on a compatibility branch.
5. Run OMH doctor/Hermes smoke plus TTF boundary and pilot compatibility checks.
6. Confirm TTF Company Core semantics are unchanged.
7. Promote the pin only after compatibility passes.

If OMH adds a feature that duplicates TTF execution infrastructure, prefer retiring the TTF duplicate after migration tests instead of keeping two owners.

## Anti-patterns

Avoid:

```text
TTF Orchestrator
  ↓
OMH loop
  ↓
Hermes goal
  ↓
TTF remediation scheduler
  ↓
OMH team
```

Prefer one owner per concern:

```text
TTF Company Contract
  ↓
OMH work organization
  ↓
Hermes runtime
  ↓
Coding owner
  ↓
Observed evidence
  ↓
TTF company decision
```
