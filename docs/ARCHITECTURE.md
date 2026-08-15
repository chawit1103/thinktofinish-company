# Architecture — ThinkToFinish Company Core over OMH + Hermes

## 1. Architecture Decision

ThinkToFinish is a **Company Governance Core**, not an alternative agent runtime and not a second generic orchestration framework.

```text
┌──────────────────────────────────────────────────────────────┐
│ Owner / Chairman                                             │
│ business goal · scope · high-risk approvals                  │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ ThinkToFinish Company Core                                   │
│ WHAT + WHY                                                   │
│ Product · Architecture · Policy · Contracts · Traceability   │
│ Risk/Approval · QA/Security Gate · Release · Company Metrics │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Oh My Hermes — preferred Work Intelligence Layer             │
│ HOW TO ORGANIZE THE WORK                                     │
│ Interview · Research · Plan · Work Coordination              │
│ Coding-owner Handoff · Long-horizon Work · Memory · QA       │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Hermes Agent — Execution OS                                  │
│ HOW TO RUN IT                                                │
│ Profiles · Kanban · Goals/Loops · Native Review · Delegation │
│ Sessions · Plugins · Gateway · Worktrees/Sandbox             │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Coding Owner                                                 │
│ HOW TO IMPLEMENT IT                                          │
│ Codex · Claude Code · pi · other explicit coding runtime     │
└──────────────────────────────────────────────────────────────┘
```

The key invariant is that every layer owns a different question. A lower layer may supply evidence or capability to a higher layer but may not silently acquire the higher layer's authority.

## 2. Authority Matrix

| Concern | Authority | Notes |
|---|---|---|
| Business goal/scope | TTF | high-impact changes follow Company Policy |
| Product Spec / requirement IDs | TTF product role | OMH interview/research can support it |
| ADRs / Architecture Contract | TTF architect role | OMH research/planning can support it |
| Company Task Contract | TTF | cannot be weakened by a work/executor layer |
| Generic interview/research workflow | OMH preferred | evidence input, not product authority |
| Work coordination / coding-owner handoff | OMH preferred | keep prepared vs observed boundary |
| Profiles/Kanban/Goals/Loops | Hermes | TTF must not rebuild scheduler/runtime internals |
| Implementation review lifecycle | Hermes native | same-card review/rework |
| Implementation | selected coding owner | Codex/Claude/pi/etc. |
| Integrated QA/Security company judgment | TTF QA role | may consume OMH QA evidence |
| Requirement traceability | TTF | Requirement → ADR → Task → Commit → PR → Test → Release |
| Release Candidate decision | TTF release governance | CI/OMH/Hermes status are evidence inputs only |
| Production approval | authorized human | default policy gate |

## 3. Company Roles

Persistent Hermes Profiles remain useful company identities, but Profile isolation must not be confused with a security sandbox.

```text
orchestrator    → company phase graph, governance, closeout
product         → Product Spec / requirements / acceptance criteria
architect       → ADRs / Decision Packet / contracts / boundaries
engineer        → Company Task Contract delivery
qa-reviewer     → native implementation review + independent QA/security judgment
release-manager → release evidence / residual risk / RC readiness
```

Role identity lives in the TTF charter. Generic planning, interview, memory, work coordination, and executor selection should use OMH/Hermes capabilities rather than be reimplemented in each charter.

## 4. Product and Architecture Authority

### Product phase

OMH `ulw-interview` and `ulw-research` are useful supporting capabilities, but the authoritative output is a TTF Product Spec containing at least:

- problem and target users,
- goals/non-goals,
- stable requirement IDs,
- acceptance criteria,
- roles/permissions,
- non-functional requirements,
- risks and assumptions,
- phase boundaries.

### Architecture phase

OMH research/planning may help compare alternatives, but the authoritative architecture artifact is a TTF Architecture Contract containing:

- ADR IDs,
- component and ownership boundaries,
- API/data contracts,
- auth/security model,
- failure/operational behavior,
- deterministic verification plan,
- Decision Packet for shared parallel-work decisions,
- residual risks.

Shared decisions must be stable before wide engineering fan-out.

## 5. Engineering Boundary

A meaningful engineering unit begins from a validated Company Task Contract.

TTF owns:

```text
Goal
Inputs
Outputs
Acceptance Criteria
Verification
Risk
Assignee/Review expectations
Security expectations
Requirement IDs
```

OMH may then organize execution, choose/prepare a coding-owner handoff, coordinate independent lanes, maintain bounded project memory, and observe execution.

Hermes owns runtime mechanics: Kanban, Profiles, session control, delegation, worktrees, Goals/Loops, and review status.

The coding owner edits code and runs implementation verification.

## 6. Native Review Model

New TTF projects use Hermes native same-card implementation review:

```text
running implementation
        ↓
kanban_request_review(reviewer="qa-reviewer")
        ↓
review
  ├─ approve → done
  └─ request_changes → original implementer → review
```

`blocked` is reserved for genuine external/safety stops, not ordinary review feedback.

Do not combine same-card review with a pre-created review child for the same implementation phase. Dedicated downstream QA/Security or Release cards are different company phases and remain separate cards.

The old TTF deterministic transition engine is retained only for compatibility with boards created under the pre-native review protocol. It is disabled by default.

## 7. Macro Company Graph

Kanban remains the macro company graph, but TTF should create **company-sized work packages**, not mirror every OMH workflow step.

```text
Product Spec
      ↓
Architecture Contract + Decision Packet
      ↓
Engineering Work Packages (2–4 where parallelism is real)
      ↓
Integration
      ↓
Integrated QA + Security
      ↓
Release Evidence
      ↓
Company Closeout / RC decision
```

Each implementation/integration package can contain an OMH work process internally and uses Hermes native review.

This prevents orchestration nesting such as TTF cards reproducing OMH task lists which themselves reproduce Hermes delegation children.

## 8. Evidence Model

TTF distinguishes three concepts:

1. **Prepared intent** — plan, handoff, contract, expected verification.
2. **Observed execution evidence** — actual commit, PR, test/CI receipt, review receipt, runtime observation.
3. **Company decision evidence** — policy decision, traceability coverage, residual risk acceptance, release gate outcome.

Prepared work never automatically upgrades itself to observed evidence.

Company Evidence Graph:

```text
Requirement → ADR → Task → Commit → PR → Test → Release
```

A release decision can consume OMH/Hermes evidence but TTF remains the authority that decides whether coverage and policy are sufficient.

## 9. Security Boundaries

Profiles are identities/state boundaries, not full filesystem sandboxes.

TTF security relies on:

- least-privilege credentials per role,
- effective sandbox/worktree isolation where required,
- no production credentials for engineering workers,
- no secrets in durable task/evidence metadata,
- human gates for production/destructive/security-exception actions,
- independent judgment,
- explicit Release Evidence.

Requested isolation is not sufficient; the effective execution environment must be observable when security depends on it.

## 10. Runtime Boundary Contract

`policies/runtime-boundary.json` is the machine-readable source of truth for layer ownership.

The portable `thinktofinish_company/` package must not:

- import `hermes_cli` internals,
- depend on `kanban_db`,
- open Hermes Kanban SQLite directly,
- become a generic memory/executor/scheduler runtime.

`scripts/runtime-boundary-check.py` enforces the most important static parts of this contract.

Runtime-specific integration should be concentrated in a thin adapter/bridge when native lifecycle events or capability provisioning are necessary.

## 11. Upgrade Governance

Neither OMH nor Hermes `main` is a production/company baseline.

Recommended channels:

```text
Preview     → upstream main; compatibility observation only
Candidate   → pinned release/commit that passed TTF compatibility tests
Supported   → explicitly promoted runtime baseline
```

OMH is currently pinned to the stable v1.0.6 release commit in `runtime-boundary.json`.

The desired response to upstream feature growth is:

```text
upstream capability appears
        ↓
compatibility suite evaluates it
        ↓
if it replaces TTF execution glue safely
        ↓
delete/retire duplicated TTF infrastructure
```

Company Core semantics should change only when company-governance requirements change, not because Hermes reorganized an internal database or dispatcher.

## 12. Design Test

For any proposed TTF feature ask:

1. Is this deciding WHAT/WHY, policy, accountability, evidence sufficiency, or release authority? → probably TTF.
2. Is this generic interviewing/planning/work coordination/memory/executor handoff? → prefer OMH.
3. Is this scheduling/session/delegation/review/worktree/runtime behavior? → Hermes.
4. Is this code implementation? → coding owner.

If two layers would both own the same lifecycle transition, stop and simplify the design before adding code.
