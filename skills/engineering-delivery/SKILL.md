---
name: engineering-delivery
description: Implement a Company Task Contract in an isolated workspace, verify it with deterministic gates, and leave structured handoff evidence.
license: MIT
compatibility: Hermes Agent coding worker; worktree and goal-mode cards recommended.
metadata:
  category: engineering
  layer: company
---
# Engineering Delivery

## When to Use
Use on implementation, refactor, bug-fix, migration, or integration cards that have explicit acceptance criteria.

## Procedure
1. Read the Kanban card, parent handoffs, prior attempts, and attached Company Task Contract.
2. Call `ttf_validate_task_contract` if the contract has not been validated.
3. Work only inside the assigned workspace/worktree.
4. Implement the smallest change that satisfies the contract.
5. Add or update tests that directly prove the acceptance criteria.
6. Run all listed verification commands. A claim of success is not evidence.
7. If a gate fails, diagnose from actual output, repair, and rerun. This is the micro Loop.
8. Record trace links for task → commit/PR/test as those artifacts become known.
9. Complete the Kanban card with structured metadata: changed files, verification commands/results, dependencies, retry notes, and residual risk.
10. Never directly push to main, bypass review, expose credentials, or deploy production.

## Evidence Standard
A complete engineering handoff answers:
- What changed?
- Which acceptance criteria are satisfied?
- Which commands prove it?
- What did not get tested?
- What risk remains?

## Stop Conditions
Block/escalate when the task requires a major scope change, destructive data migration, credential change, security exception, or production-only operation.
