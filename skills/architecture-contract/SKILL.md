---
name: architecture-contract
description: Produce authoritative implementation-ready architecture and shared decision contracts.
version: 0.3.0
author: ThinkToFinish
license: MIT
compatibility: Hermes Agent software projects; OMH research/planning may support decisions.
metadata:
  category: architecture
  layer: company
---
# Architecture Contract

## Authority
The TTF `architect` role owns accepted ADRs, shared contracts, Decision Packet, security boundaries, verification plan, and residual risks. OMH research/planning is advisory evidence.

## Procedure
1. Read accepted requirement IDs and acceptance criteria.
2. Use research/planning capabilities when alternatives or external facts need investigation.
3. Choose the smallest architecture that satisfies current accepted scope.
4. Define components, data ownership, API contracts, auth/RBAC, failure behavior, observability, and operational boundaries.
5. Record important decisions as stable ADR IDs and link relevant requirements with `ttf_trace_edge`.
6. Produce a **Decision Packet** for shared choices that parallel engineering lanes must not independently reinvent: schemas, API shapes, naming, error contracts, runtime assumptions, integration boundaries.
7. Define deterministic verification surfaces: tests, builds, contract checks, migrations, smoke tests.
8. State residual risks and what would force an architecture/company decision to reopen.

## Fan-out Gate
Do not begin wide engineering fan-out while shared contracts are contradictory or unresolved. OMH/Hermes parallelism should consume a stable Decision Packet rather than create competing architectural truth.

## Pitfalls
Do not optimize hypothetical scale at the expense of an unverifiable MVP. Do not treat a generated plan as an accepted ADR until the architect has made the company decision explicit.
