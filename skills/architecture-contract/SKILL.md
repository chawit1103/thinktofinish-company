---
name: architecture-contract
description: Design implementation-ready architecture contracts.
version: 0.2.0
author: ThinkToFinish
license: MIT
compatibility: Hermes Agent software projects.
metadata:
  category: architecture
  layer: company
---
# Architecture Contract

## When to Use
Use after product requirements are stable enough to constrain implementation and before parallel engineering begins.

## Procedure
1. Read requirement IDs and acceptance criteria.
2. Choose the smallest architecture that satisfies current scope.
3. Define components, data ownership, API contracts, auth/RBAC, failure behavior, and observability.
4. Identify decisions that are reversible versus high-cost to reverse.
5. Record important decisions as stable ADR IDs.
6. Link each relevant requirement to its ADR using `ttf_trace_edge`.
7. Define engineering boundaries so backend, frontend, and data tasks can run in parallel without contract drift.
8. State deterministic verification surfaces: tests, build commands, contract checks, migrations, or smoke tests.

## Architecture Output
- Context and constraints
- Component boundaries
- Data model
- API/interface contracts
- Security model
- Operational model
- ADRs with IDs
- Verification plan
- Known residual risks

## Pitfalls
Do not optimize for hypothetical scale at the cost of an unverifiable MVP. Do not allow implementation to begin if shared contracts are still contradictory.
