---
name: qa-release-gate
description: Perform native implementation review and independent company QA/release judgment.
version: 0.3.0
author: ThinkToFinish
license: MIT
compatibility: Hermes Agent native review lifecycle; OMH QA evidence may be consumed.
metadata:
  category: quality
  layer: company
---
# QA and Release Gate

## Two Review Levels

### Implementation review
Inside Hermes same-card review:
1. Read the original Company Task Contract and accepted Product/Architecture decisions.
2. Inspect actual change/diff and verification evidence.
3. Re-run/verify deterministic checks where practical.
4. Approve with `kanban_complete` only when implementation is satisfactory.
5. For ordinary rework call `kanban_request_changes(reason=...)`; do not generic-block and do not invoke the legacy TTF transition engine.

### Integrated QA/Security company gate
This is a separate downstream company task. Evaluate system-level acceptance, regression/failure paths, authorization/privacy, secrets, injection/deserialization, dependencies, operational behavior, and residual risk.

OMH `ulw-qa` can generate adversarial evidence, but its result does not automatically pass this gate.

## Release Gate
1. Verify CI/tests with observed evidence.
2. Verify independent review state.
3. Require integrated QA/Security acceptance.
4. Require zero Critical/High unresolved findings unless policy was explicitly changed through authorized human approval.
5. Call `ttf_requirement_coverage` and identify missing Requirement → ADR → Task → Commit/PR → Test → Release paths.
6. Declare residual risk explicitly.
7. Construct release evidence and call `ttf_release_gate`.

Production remains a separate human-gated action even when Release Candidate evidence passes.

## Evidence Boundary
A green CI badge, OMH QA success, Hermes task completion, or producer claim is an evidence input, not by itself a release decision.
