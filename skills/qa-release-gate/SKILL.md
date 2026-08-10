---
name: qa-release-gate
description: Independently verify changes and release readiness.
version: 0.2.0
author: ThinkToFinish
license: MIT
compatibility: Hermes Agent reviewer or release profile with project and CI access.
metadata:
  category: quality
  layer: company
  hermes:
    tags: [quality, review, release]
    related_skills: [engineering-delivery, company-orchestrator]
---
# QA and Release Gate

## When to Use
Use after implementation/integration and before a release candidate is declared ready.

## Independent Review
1. Do not rely on the producer's "done" statement.
2. Re-read requirements and acceptance criteria.
3. Inspect the change/diff and verification evidence.
4. Run or verify deterministic checks appropriate to the project.
5. Check regression risk and failure-path behavior.
6. Check security evidence. Critical/high findings must be zero unless policy explicitly changes through a human-approved exception.
7. Call `ttf_requirement_coverage` and identify missing requirement → task → PR → test → release paths.
8. Construct release evidence and call `ttf_release_gate`.

## Outcomes
- `approved`: write the structured `ttf_review` JSON comment, then complete the review card so its children can advance.
- `release_candidate_ready`: evidence satisfies company policy.
- `changes_requested`: write a structured `ttf_review` JSON comment with reviewed commit and actionable findings, then use an untyped/generic block. The transition engine creates the remediation/re-review pair and rewires downstream gates.
- `blocked`: for a retained policy/capability stop, emit no `changes_requested` verdict and use block kind `needs_input` or `capability`.
- Production remains a separate human-gated action even when a release candidate is ready.

## Pitfalls
Do not turn warnings into invisible risk. Do not waive tests or security because deadlines are tight. Do not approve a release with incomplete traceability unless company policy is explicitly changed by an authorized human.
