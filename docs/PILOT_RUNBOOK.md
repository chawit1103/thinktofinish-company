# Mini HRMS Pilot Runbook — Company Core + OMH + Hermes

## Objective

Prove that ThinkToFinish can take a business-level goal to a governed Release Candidate while keeping authority boundaries clean:

- TTF owns company requirements, architecture, policy, traceability, QA/Security judgment, and release decision.
- OMH organizes work when useful.
- Hermes runs Profiles/Kanban/Goals/Loops/native review/delegation/workspaces.
- Coding owners implement code.

## 1. Bootstrap

Install/configure the recommended stack:

```bash
./scripts/bootstrap-company.sh
```

Verify:

```bash
./scripts/doctor.sh
./scripts/compatibility-check.sh
```

The runtime boundary check should report OMH pinned to the supported stable baseline and the legacy TTF transition engine disabled by default.

## 2. Prepare Project

```bash
mkdir -p ~/Projects/mini-hrms
cd ~/Projects/mini-hrms
git init
printf '# Mini HRMS\n' > README.md
git add README.md
git commit -m 'chore: initialize pilot'
```

## 3. Create Company Board

From the TTF repo:

```bash
./scripts/create-pilot.sh ~/Projects/mini-hrms mini-hrms
```

The script sets the board's default workdir to the project Git repository.

## 4. Expected Staged Graph

The kickoff orchestrator creates only the early governance stages first:

```text
Kickoff
   ↓
Product Spec
   ↓
Architecture Contract + Decision Packet
   ↓
Engineering Work Planner
```

The second orchestrator reads actual Product/Architecture evidence before creating engineering packages.

Expected macro graph:

```text
Product
  ↓
Architecture
  ↓
Engineering Work Packages
  ↓
Integration
  ↓
Integrated QA + Security
  ↓
Release Evidence
  ↓
Company Closeout
```

Do not expand every OMH sub-work item into a parallel Kanban graph.

## 5. Product Phase

The `product` Profile may use OMH interview/research capabilities to resolve uncertainty.

Definition of Done includes:

- stable requirement IDs,
- explicit acceptance criteria,
- roles/permissions,
- MVP vs Later vs Out of Scope,
- risks and assumptions,
- requirement trace nodes,
- authoritative TTF Product Spec handoff.

OMH notes are supporting evidence, not the Product Spec by themselves.

## 6. Architecture Phase

The `architect` Profile may use OMH research/planning, but must produce:

- ADR IDs,
- component/data/API boundaries,
- auth/RBAC/security model,
- shared Decision Packet,
- deterministic verification plan,
- residual risks,
- requirement→ADR traceability.

Engineering fan-out should not begin while shared decisions are contradictory.

## 7. Engineering Phase

Each engineering work package must include a validated TTF Company Task Contract.

OMH may organize work and select/prepare a coding-owner handoff. The selected coding owner performs implementation.

The normal implementation lifecycle is:

```text
Implement
  ↓
run deterministic verification
  ↓
kanban_request_review(reviewer="qa-reviewer")
  ↓
Hermes native review
  ├─ approve → done
  └─ request_changes → original implementer → re-review
```

Do not use the legacy TTF transition engine for ordinary feedback and do not create a second review-child lane for the same implementation phase.

## 8. Integration

Integration is a meaningful work package, not merely a merge action. It verifies cross-component contracts and uses the same native implementation review lifecycle.

Only reviewed/done implementation packages should release integration work.

## 9. Integrated QA + Security

This is a separate company gate. It is not the same as implementation code review.

Review at least:

- requirement acceptance coverage,
- regression/failure paths,
- RBAC/authorization boundaries,
- secrets handling,
- injection/deserialization surfaces,
- dependency/supply-chain risk where relevant,
- audit behavior,
- untested/residual risk.

OMH `ulw-qa` may be used as an adversarial evidence generator. Its success does not automatically mark this company gate passed.

## 10. Release Evidence

The `release-manager` checks:

- CI/tests pass with actual evidence,
- independent review is satisfied,
- integrated QA/Security accepted,
- zero unresolved Critical/High findings under default policy,
- Requirement → ADR → Task → Commit → PR → Test → Release coverage,
- residual risks declared,
- human-gated actions remain unperformed without approval.

The release target for the pilot is **Release Candidate**, not production.

## 11. Company Closeout

The orchestrator calls TTF traceability and release-gate tools and records company metrics.

A green Kanban board alone is insufficient. A green OMH QA result alone is insufficient. A coding owner saying "done" alone is insufficient.

## 12. Legacy Boards

If an older board still uses:

```text
review child → generic block → ttf_review comment → TTF transition engine
```

migrate it separately. Do not enable legacy autopilot on a new pilot merely because the compatibility script still exists.

## 13. Success Criteria

The pilot succeeds when:

- no company authority is accidentally delegated to OMH/Hermes/coding runtime,
- execution glue is not duplicated,
- implementation review cycles autonomously through native Hermes review,
- Company Evidence Graph is complete enough for RC,
- production remains human-gated,
- TTF core remains independent of Hermes Kanban database internals.
