# Mini-HRMS Pilot Runbook

## Objective

Prove that one owner goal can progress through Agent + Loop + Graph + Governance to a Release Candidate with minimal human intervention.

## Before launch

```bash
./scripts/doctor.sh
./scripts/bootstrap-hermes.sh
```

Prepare a Git repo with at least one commit. Confirm the Hermes model/provider works in each profile you intend to use.

## Launch

```bash
./scripts/create-pilot.sh /absolute/path/to/mini-hrms mini-hrms
./scripts/enable-kanban-autopilot.sh --profile orchestrator mini-hrms
hermes -p orchestrator gateway start
hermes dashboard
```

The pilot script sets the board's default workdir to the Git repo. Hermes can therefore keep task work isolated in project workspaces/worktrees.

## Expected graph evolution

### Phase A — intake

`Orchestrate Mini HRMS to Release Candidate` runs under `orchestrator`.

It should create:

1. Product Discovery / Product Spec (`product`)
2. Architecture Contract (`architect`, parent=Product)
3. Engineering Graph Planner (`orchestrator`, parent=Architecture)

The kickoff then completes.

### Phase B — engineering graph

After Architecture completes, the second orchestrator reads upstream handoffs and should create:

- 2–4 scoped implementation producer cards (`engineer`) where parallelism is safe, each with a pre-created read-only reviewer child (`qa-reviewer`)
- Integration producer, parented on approved implementation reviews, with its own pre-created reviewer child
- Independent QA/Security card (`qa-reviewer`), parent=approved Integration reviewer child
- Release Evidence card (`release-manager`), parent=QA/Security
- Company Closeout card (`orchestrator`), parent=Release Evidence

Implementation producers use normal Kanban cards, not goal-mode: their terminal outcome is a verified `review-required:` commit handoff. Goal-mode is reserved for an orchestration/research card whose completion does not depend on a downstream child.

The board-scoped transition engine reads structured reviewer verdicts. A `changes_requested` verdict creates a remediation/re-review pair, rewires downstream dependencies to the new review, and archives the rejected review as evidence. It permits one active transition per Git checkout and automatically replaces a deferred stale verdict with a fresh-review card. Three rejected remediation or stale-review generations trigger one retained owner-input gate while downstream work remains gated. Typed `needs_input` and `capability` blocks are never automated.

For a legacy board, migrate every reviewer profile to the `ttf_review` contract before takeover, then run `./scripts/enable-kanban-autopilot.sh --profile orchestrator --replace-legacy mini-hrms`. This pauses matching active legacy graph jobs across every Hermes profile. Re-run it after plugin updates to refresh the board's installed engine copy.

### Phase C — release closeout

The final orchestrator must check:

- requirement coverage
- CI and test evidence
- independent review
- security status
- residual risks
- release gate result

The expected terminal state is **Release Candidate Ready**, not production deployed.

## What the owner should intervene on

Intervene only for a real blocker or policy gate such as:

- major scope change
- destructive migration
- credential change
- paid service purchase
- production database write
- security exception
- production deployment

Technical choices inside approved scope should normally remain autonomous.

## What to watch

```bash
hermes kanban --board mini-hrms list
hermes kanban --board mini-hrms watch
hermes kanban --board mini-hrms diagnostics
```

In the dashboard, inspect Run History and completion metadata rather than trusting final prose.

## Pilot scorecard

A successful V0.1 run demonstrates:

- root goal accepted once
- staged graph created without manual task-by-task prompting
- correct role routing
- dependency-aware parallelism
- repair loops on implementation failures
- producer/reviewer separation
- requirement traceability
- release evidence gate
- human intervention only at legitimate policy gates

After the run, ask the Company Layer for `ttf_metrics_summary(project="mini-hrms")` and record what required manual intervention. Those gaps determine V0.2 work.
