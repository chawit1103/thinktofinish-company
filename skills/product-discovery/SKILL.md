---
name: product-discovery
description: Turn software ideas into authoritative evidence-backed Product Specs.
version: 0.3.0
author: ThinkToFinish
license: MIT
compatibility: Hermes Agent; Oh My Hermes interview/research recommended when useful.
metadata:
  category: product
  layer: company
---
# Product Discovery

## Authority
The TTF `product` role owns the authoritative Product Spec. OMH `ulw-interview` / `ulw-research` may be used as supporting capabilities but do not automatically become company requirements.

## Procedure
1. State the business/user outcome and target users.
2. Separate known facts, assumptions, open questions, and evidence gaps.
3. Use OMH interview/research or Hermes-native research when it materially improves the decision.
4. Reconcile supporting evidence into explicit company scope: Must / Later / Out of scope.
5. Write stable requirement IDs such as `HRMS-REQ-001`.
6. Give every requirement concrete acceptance criteria.
7. State roles/permissions, non-functional requirements, risks, assumptions, and phase boundaries.
8. Record each accepted requirement with `ttf_trace_node(project, "requirement", id, ...)`.
9. Produce the authoritative Product Spec so Architecture does not have to reconstruct chat/workflow state.

## Evidence Boundary
- Interview notes ≠ accepted requirement.
- Research result ≠ company scope decision.
- OMH plan ≠ Product Spec.
- Only requirements accepted into the Product Spec gain TTF requirement authority.

## Pitfalls
Do not invent regulatory requirements as facts. Do not let Phase 2 leak into MVP acceptance criteria. Do not hand Architecture a prose-only wish list without requirement IDs.
