# ThinkToFinish Company Core

**Turn Hermes + Oh My Hermes into a governed AI Software Company.**

ThinkToFinish (TTF) is the **Company Governance layer** above Oh My Hermes (OMH) and Hermes Agent. It deliberately does not rebuild the agent runtime, generic work orchestration, memory engine, executor router, worktree manager, or Kanban scheduler.

```text
Owner / Chairman
      │
      ▼
ThinkToFinish Company Core
WHAT + WHY
Product Governance · Architecture Governance · Policy
Task Contracts · Traceability · Risk/Approval · Release · Metrics
      │
      ▼
Oh My Hermes (preferred Work Intelligence layer)
HOW TO ORGANIZE WORK
Interview · Research · Planning · Coordination · Coding-owner handoff
Long-horizon workflows · Project memory · Execution observation · Adversarial QA
      │
      ▼
Hermes Agent
HOW TO RUN IT
Profiles · Kanban · Goals/Loops · Native Review · Delegation
Sessions · Plugins · Gateway · Worktrees/Sandbox
      │
      ▼
Codex / Claude Code / pi / other coding owner
HOW TO IMPLEMENT IT
```

The core rule is:

> **ThinkToFinish owns WHAT and WHY. OMH owns HOW TO ORGANIZE THE WORK. Hermes owns HOW TO RUN IT. The selected coding owner owns HOW TO IMPLEMENT IT.**

This boundary is intentional. Hermes and OMH evolve quickly; upstream capability growth should normally let ThinkToFinish **delete execution glue**, not add more of it.

## What ThinkToFinish owns

- Business goal and scope authority
- Product Spec with stable requirement IDs and acceptance criteria
- Architecture Contract, ADRs, Decision Packet, security boundaries
- Company Task Contract / Definition of Done
- Autonomous / human-approval / forbidden policy
- Separation of duties and independent judgment
- Requirement → ADR → Task → Commit → PR → Test → Release traceability
- Integrated QA/Security company gate
- Release Evidence and Release Candidate decision
- Company metrics and governance learning

## What ThinkToFinish does not own

New projects must not depend on TTF implementations of:

- Kanban scheduling or graph dispatch internals
- generic Goal/Loop runtime
- generic memory runtime
- generic coding-executor routing
- worktree management
- Hermes session coordination
- ordinary implementation review/rework transitions
- direct mutation of Hermes `kanban.db`

The existing deterministic transition engine is retained only as a **legacy-board compatibility fallback** for boards created before Hermes gained the native review/rework lifecycle. It is disabled by default for new projects.

## Supported Work Layer

The current TTF-supported OMH baseline is pinned in `policies/runtime-boundary.json`:

```text
Oh My Hermes v1.0.6
commit 0106a636d7c971408e9caf634b5e21a471fc5082
channel stable
```

TTF does not follow OMH `main` automatically. The same rule applies to Hermes: runtime upgrades are compatibility-tested before being promoted.

## Quick Start

Prerequisites:

- Hermes Agent installed and configured
- Git
- Python 3.11+
- `curl` for the pinned OMH installer

Bootstrap the recommended stack:

```bash
./scripts/bootstrap-company.sh
```

This:

1. installs the pinned stable OMH baseline,
2. runs `omh setup` and `omh doctor`,
3. creates/updates the ThinkToFinish Hermes Profiles,
4. installs the portable TTF Company Core into those Profiles,
5. runs the lightweight layered compatibility check.

For a non-interactive or already-configured OMH host:

```bash
./scripts/bootstrap-company.sh --skip-omh-setup
```

To install only OMH:

```bash
./scripts/install-omh.sh
```

To inspect the local stack:

```bash
./scripts/doctor.sh
./scripts/compatibility-check.sh
```

## Fresh Ubuntu Machine

For a clean Ubuntu machine, **Ubuntu 24.04 LTS or newer is recommended** because ThinkToFinish requires Python 3.11+ and Ubuntu 24.04 ships a sufficiently new system Python. Ubuntu 22.04 can still be used, but its default Python 3.10 does not satisfy the TTF prerequisite without an additional Python installation.

Do not run Hermes, OMH, or TTF setup commands with `sudo`. Use `sudo` only for OS package installation.

### 1. Install base OS packages

```bash
sudo apt update
sudo apt install -y git curl ca-certificates
```

Confirm the local tools:

```bash
git --version
curl --version
python3 --version
```

`python3 --version` must report **3.11 or newer** for the TTF scripts.

### 2. Install Hermes Agent

Use the official Hermes Linux installer:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Reload the shell environment:

```bash
source ~/.bashrc
```

Then configure Hermes and verify the installation:

```bash
hermes setup
hermes doctor
hermes --version
```

The Hermes installer manages its own runtime dependencies. TTF still checks the host `python3` because its bootstrap, compatibility, and MCP smoke scripts execute with the system Python.

### 3. Clone ThinkToFinish

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/chawit1103/thinktofinish-company.git
cd thinktofinish-company
```

### 4. Bootstrap the complete stack

For a new test machine, run the full bootstrap including the OMH/Hermes smoke test:

```bash
./scripts/bootstrap-company.sh --omh-smoke
```

The bootstrap will:

```text
Hermes already installed/configured
        ↓
Install pinned OMH v1.0.6
        ↓
OMH setup + doctor + Hermes smoke
        ↓
Create/update TTF company Profiles
        ↓
Install TTF Company Core in each Profile
        ↓
Run layered compatibility checks
```

`omh setup` may ask about model/provider aliases. Review those choices rather than blindly replacing an existing Hermes model configuration.

### 5. Verify all three layers

```bash
hermes --version
omh --version
omh doctor
./scripts/doctor.sh
./scripts/compatibility-check.sh
```

A successful layered check ends with:

```text
TTF_COMPATIBILITY_OK
```

If OMH installed successfully but `omh` is not found, start a new shell first. The TTF installer also probes common locations such as `~/.local/bin`.

### 6. Optional: create a disposable pilot project

```bash
mkdir -p ~/Projects/mini-hrms
cd ~/Projects/mini-hrms
git init
git config user.name "TTF Pilot"
git config user.email "ttf-pilot@localhost"
printf '# Mini HRMS\n' > README.md
git add README.md
git commit -m 'chore: initialize pilot'

cd ~/Projects/thinktofinish-company
./scripts/create-pilot.sh ~/Projects/mini-hrms mini-hrms
```

Then inspect the board/runtime:

```bash
hermes dashboard
```

or start an orchestrator gateway if you want the persistent Hermes runtime:

```bash
hermes -p orchestrator gateway start
```

For a first Ubuntu validation, keep the pilot disposable and avoid production credentials or real employee/customer data.

### Ubuntu upgrade / re-test flow

After later updates to Hermes or TTF:

```bash
hermes update

cd ~/Projects/thinktofinish-company
git switch main
git pull
./scripts/bootstrap-company.sh --skip-omh-setup --omh-smoke
./scripts/compatibility-check.sh
```

This keeps OMH on the TTF-supported pinned baseline instead of silently following OMH `main`.

## Company Roles

ThinkToFinish keeps company responsibility separate from generic workflow mechanics:

| Profile | Company authority |
|---|---|
| `orchestrator` | scope-aware company graph, routing, governance, closeout |
| `product` | authoritative Product Spec, requirement IDs, acceptance criteria |
| `architect` | authoritative ADRs/contracts/shared decisions/security boundaries |
| `engineer` | delivery against a Company Task Contract; may use OMH/coding owners |
| `qa-reviewer` | independent implementation review plus integrated QA/Security judgment |
| `release-manager` | release evidence, traceability, residual risk, RC readiness |

OMH workflows are **capabilities used by these roles**, not replacement company authorities. For example, `ulw-interview` can strengthen Product Discovery, but its output is not authoritative until the `product` role turns it into the TTF Product Spec.

## Review Model

New projects use **Hermes native same-card implementation review**:

```text
Engineer implements + verifies
        │
        ▼
kanban_request_review(reviewer="qa-reviewer")
        │
        ▼
Hermes REVIEW
   ┌────┴─────────┐
approve       request_changes
   │               │
 done          original implementer
                   │
                   └──────→ review again
```

Use `kanban_block` only for a genuine external stop such as human approval, production/destructive action, security exception, or a required unavailable capability.

Do **not** create a second pre-created review child for the same implementation phase while also using same-card review.

Separate downstream company gates remain first-class:

```text
Product Spec
    ↓
Architecture Contract + Decision Packet
    ↓
Engineering Work Packages
    ↓ native implementation review
Integration
    ↓ native implementation review
Integrated QA + Security
    ↓
Release Evidence
    ↓
Company Closeout / RC decision
```

OMH may organize work inside an Engineering Work Package, but the Hermes Kanban board should not mirror every OMH internal substep card-for-card.

## Evidence Standard

ThinkToFinish distinguishes prepared intent from observed evidence. A prepared plan, prepared coding handoff, green-looking status, or agent-reported completion does not prove execution or verification.

The Company Evidence Graph is:

```text
Requirement → ADR → Task → Commit → PR → Test → Release
```

A Release Candidate normally requires:

- acceptance criteria satisfied,
- CI/tests verified,
- independent review satisfied,
- integrated security evidence accepted,
- zero unresolved Critical/High findings under default policy,
- traceability complete,
- residual risks declared,
- release policy satisfied.

OMH QA success and Hermes task completion are useful evidence inputs, but neither alone is a TTF release decision.

## Pilot

Prepare a Git repository with at least one commit, then:

```bash
./scripts/create-pilot.sh ~/Projects/mini-hrms mini-hrms
```

Expected high-level graph:

```text
Product → Architecture → Engineering Work Packages
                         ↓
                    Integration
                         ↓
                   QA + Security
                         ↓
                  Release Evidence
                         ↓
                  Company Closeout
```

Implementation packages use native review loops internally rather than review-child/remediation graphs.

## Runtime Boundary

The machine-readable boundary is `policies/runtime-boundary.json`.

CI enforces that the portable `thinktofinish_company/` core does not import Hermes internals or address Hermes Kanban SQLite storage directly:

```bash
make boundary-check
```

The intent is to keep runtime-specific integration thin. When Hermes changes, compatibility impact should be isolated to adapters/integration surfaces rather than Company Core semantics.

## Legacy Transition Engine

`scripts/kanban-transition-engine.py` and its regression suite remain for migration support only.

Do not enable it on a newly-created board. Existing boards that still encode the old `blocked + ttf_review + remediation child` protocol can be migrated separately after confirming their review state and evidence lineage.

## Development

Run the repository tests:

```bash
make test
make boundary-check
make smoke
```

Static layered compatibility check:

```bash
./scripts/compatibility-check.sh --static
```

Installed-stack check:

```bash
./scripts/compatibility-check.sh
```

## Design Principle

```text
Hermes capability ↑
        ↓
TTF infrastructure code ↓
        ↓
TTF company intelligence ↑
```

ThinkToFinish should remain valuable even if the execution runtime changes. Hermes is the preferred execution OS and OMH the preferred work-intelligence layer, but Company Policy, Product/Architecture authority, traceability, risk/approval, and release governance remain TTF concerns.
