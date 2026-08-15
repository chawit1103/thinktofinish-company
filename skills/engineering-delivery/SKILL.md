---
name: engineering-delivery
description: Deliver a Company Task Contract using OMH/Hermes/coding-owner capabilities and native review.
version: 0.3.0
author: ThinkToFinish
license: MIT
compatibility: Hermes Agent native review lifecycle; Oh My Hermes recommended for work/coding-owner organization.
metadata:
  category: engineering
  layer: company
---
# Engineering Delivery

## When to Use
Use on implementation, refactor, bug-fix, migration, or integration work packages with explicit acceptance criteria.

## Procedure
1. Read Product/Architecture handoffs, Decision Packet, Kanban task, prior attempts, and Company Task Contract.
2. Call `ttf_validate_task_contract` when the contract has not been validated.
3. Use OMH to organize work or prepare/select an explicit coding-owner handoff when useful; the Company Task Contract remains authoritative.
4. Work only in the effective assigned workspace/worktree/sandbox.
5. Implement the smallest change that satisfies the full contract.
6. Add/update tests that directly prove acceptance criteria and run all listed deterministic verification.
7. Diagnose/repair failures without weakening tests, security, or scope.
8. Record task → commit/PR/test trace links only when the artifacts are real/observed.
9. Finish producer verification with structured handoff metadata, then call Hermes native `kanban_request_review(..., reviewer="qa-reviewer")`.
10. If changes are requested, resume the same task as the original implementer, address findings plus the original full contract, rerun verification, and request review again.

## Review Rule
Do not create or depend on a TTF remediation/re-review child graph for ordinary feedback. Do not use `kanban_block` as a review status.

## Evidence Standard
A complete engineering handoff states what changed, which acceptance criteria are satisfied, the commands/results that prove it, what remains untested, and residual risk. A prepared OMH coding handoff is not evidence that implementation occurred.

## Stop Conditions
Block/escalate only for a genuine human/safety/capability boundary such as major scope change, destructive data migration, credential change, security exception, production-only operation, or unavailable required capability.
