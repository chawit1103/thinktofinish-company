---
name: product-discovery
description: Turn a rough software idea into evidence-backed requirements and a product specification suitable for autonomous delivery.
license: MIT
compatibility: Hermes Agent; web/research tools are useful but not mandatory.
metadata:
  category: product
  layer: company
---
# Product Discovery

## When to Use
Use before architecture or coding when the request is a product idea, a business problem, or an underspecified feature.

## Procedure
1. State the user outcome and target users.
2. Separate known facts, assumptions, and open questions.
3. Research the minimum external evidence needed for the decision when tools are available.
4. Define scope as Must / Later / Out of scope.
5. Write requirements with stable IDs such as `HRMS-REQ-001`.
6. Give every requirement concrete acceptance criteria.
7. Record each requirement with `ttf_trace_node(project, "requirement", id, ...)`.
8. Produce a Product Spec that an architect and orchestrator can consume without reconstructing the conversation.

## Product Spec Minimum
- Problem and target user
- Goals and non-goals
- Functional requirements with IDs
- Non-functional requirements
- User roles and permissions
- Acceptance criteria
- Risks and assumptions
- Phase boundaries

## Pitfalls
- Do not invent regulatory requirements as facts.
- Do not mix Phase 2 features into MVP acceptance criteria.
- Do not hand architecture a prose-only wish list without requirement IDs.
