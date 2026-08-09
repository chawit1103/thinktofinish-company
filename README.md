# ThinkToFinish Company Layer for Hermes

**Turn Hermes Agent into a governed AI Software Company.**

ThinkToFinish Company Layer is a portable-first governance and delivery layer for Hermes Agent. It does **not** replace Hermes Kanban, Profiles, Goal loops, Skills, worktrees, delegation, Codex runtime, webhooks, or dashboards. It adds the company semantics that sit above those primitives:

- **Policy** — what AI may do autonomously, what needs human approval, and what is forbidden.
- **Task Contract** — a consistent Definition of Done for every work item.
- **Traceability** — Requirement → Task → Commit → PR → Test → Release.
- **Release Evidence** — deterministic evidence required before a release is considered ready.
- **Metrics** — cycle time, retries, first-pass rate, human intervention, cost, and autonomous completion.

The operating model is:

```text
Agent      = Capability
Loop       = Reliability
Graph      = Organization
Governance = Company
```

or, end-to-end:

```text
Owner / Chairman
       │
       ▼
ThinkToFinish Company Layer
 Policy · Contracts · Evidence · Metrics
       │
       ▼
Hermes Kanban Graph
       │
 ┌─────┼───────────────┐
 ▼     ▼               ▼
Agent  Agent           Agent
 │      │               │
Loop   Loop            Loop
 └──────┼───────────────┘
        ▼
 Integration → Review → Security → CI
        │
        ▼
   Release Candidate
        │
  Human Gate for high-risk actions
        │
        ▼
    Production
```

## What V0.1 provides

### Portable Agent Plugin

The repo is an Agent Plugins v1 portable package:

```text
plugin.json
mcp.json
skills/
server.py
```

Hermes loads the read-only namespaced skills and starts the local stdio MCP server. The MCP server has **zero third-party runtime dependencies**; Python 3.11+ is sufficient.

### 11 company tools

| Tool | Purpose |
|---|---|
| `ttf_company_status` | Company Layer status and principles |
| `ttf_policy_check` | Autonomous / human approval / forbidden classification |
| `ttf_validate_task_contract` | Validate task Definition of Done before execution |
| `ttf_trace_node` | Record Requirement / ADR / Task / Commit / PR / Test / Release |
| `ttf_trace_edge` | Link delivery evidence into a traceability graph |
| `ttf_trace_query` | Inspect incoming/outgoing evidence links |
| `ttf_trace_path` | Find an evidence path to a target artifact type |
| `ttf_requirement_coverage` | Measure requirement coverage through delivery |
| `ttf_release_gate` | Evaluate CI/test/review/security/traceability evidence |
| `ttf_metrics_record` | Record terminal task metrics |
| `ttf_metrics_summary` | Summarize company delivery/autonomy KPIs |

### Company skills

- `company-orchestrator` — use Hermes Kanban as the macro graph; never implement production code from the orchestrator.
- `product-discovery` — create stable requirement IDs and acceptance criteria.
- `architecture-contract` — produce ADRs, boundaries, contracts, and verification plans.
- `engineering-delivery` — implement in a worktree/branch, use goal loops and deterministic gates, leave evidence.
- `qa-release-gate` — independent review, security, traceability, and release-candidate evidence.

### Mini-HRMS pilot

A ready-to-run pilot goal is included under `examples/mini-hrms/` to prove the complete operating model on a bounded app:

- Authentication
- Employee management
- Leave request/approval
- HR / Manager / Employee RBAC
- Basic audit log
- Minimal dashboard
- Payroll explicitly out of scope

The expected endpoint is a **Release Candidate**, not an automatic production deployment.

---

# Quick start

## 1. Prerequisites

You need:

- Hermes Agent installed and configured with a working model/provider
- Python 3.11+
- Git
- A local Git project that Hermes may modify

Check your machine:

```bash
./scripts/doctor.sh
```

If Hermes is not installed/configured yet, complete Hermes setup first.

## 2. Bootstrap the AI company

From this repo:

```bash
./scripts/bootstrap-hermes.sh
```

This creates these Hermes Profiles if they do not already exist and installs their ThinkToFinish role charters:

```text
orchestrator
product
architect
engineer
qa-reviewer
release-manager
```

It installs/enables ThinkToFinish Company Layer for each profile and for the default profile. It also installs a managed ThinkToFinish role-charter block into each specialist profile's `SOUL.md` without replacing other existing SOUL content.

The intended role separation is:

| Profile | Responsibility |
|---|---|
| `orchestrator` | Understand goal, decompose, route, monitor, re-plan, escalate |
| `product` | Research, requirements, Product Spec, acceptance criteria |
| `architect` | Architecture, ADRs, API/data contracts, security boundaries |
| `engineer` | Implementation, tests, repair loops, PR-ready evidence |
| `qa-reviewer` | Independent review, regression, security, release readiness |
| `release-manager` | CI/release evidence, RC coordination, production human gate |

**Important:** a Hermes Profile is an identity/state boundary, not a security sandbox. Use an isolated terminal backend/Codex sandbox and separate credentials for sensitive roles.

## 3. Hermes Kanban setup

The governed pilot does **not** require global Auto Decompose. It creates a dispatcher-spawned `orchestrator` kickoff card; Hermes automatically injects the task-scoped Kanban tools that let that worker create/link child cards. This avoids changing your global Kanban behavior.

Optional: enable the **`kanban` toolset** on the `orchestrator` profile only if you also want ordinary interactive chats under that profile to inspect/route the board.

Recommended engineering policy:

- One Board = one project
- Coding tasks use `worktree`
- Engineering cards use goal mode when the task requires iterative repair
- Reviewer is not the producer
- No direct push to `main`
- Production credentials are not available to `engineer`

## 4. Prepare a pilot project

Use an existing Git repo, or make a small empty one:

```bash
mkdir -p ~/Projects/mini-hrms
cd ~/Projects/mini-hrms
git init
printf '# Mini HRMS\n' > README.md
git add README.md
git commit -m 'chore: initialize pilot'
```

## 5. Create the Mini-HRMS goal

From the `thinktofinish-company` repo:

```bash
./scripts/create-pilot.sh ~/Projects/mini-hrms mini-hrms
```

The script creates/switches the `mini-hrms` board, sets that board's default workdir to the target Git repo, and creates a **goal-mode orchestrator kickoff card**. If the target repo has no existing supported project context file, it also copies `templates/PROJECT_AGENTS.md` to the target as `AGENTS.md`; it never overwrites or auto-commits existing project instructions.

The kickoff card creates Product → Architecture → a second orchestrator planning gate. That second orchestrator reads the actual upstream handoffs and builds the concrete Engineering DAG, QA/Security, Release Evidence, and Company Closeout cards. This staged graph is more governed than sending the raw product goal directly through generic Auto Decompose, while still using Hermes-native Kanban dependencies and Goal loops.

## 6. Run the company

Keep the Hermes gateway running:

```bash
hermes gateway start
```

Open the dashboard:

```bash
hermes dashboard
```

You should see the kickoff orchestrator create the first staged dependency graph. After Product and Architecture finish, the second orchestrator card should wake and create the implementation/integration/review/release graph. Independent tasks may run in parallel; dependent tasks wait for parent handoffs.

The intended pattern is:

```text
Kanban Graph = macro workflow
Goal Loop    = micro workflow
```

For example, an engineering card should iterate:

```text
Implement → test/gate → fail → diagnose → repair → retest → pass
```

while the project graph coordinates:

```text
Research → Product Spec → Architecture
                      ├→ Backend ─┐
                      ├→ Frontend ├→ Integration → Review → Security → RC
                      └→ Data ────┘
```

---

# Verify the Company Layer

## Raw MCP smoke test

```bash
python3 scripts/mcp-smoke.py
```

Expected:

```text
MCP_SMOKE_OK 11
```

The smoke test checks both a legacy MCP initialization path and the current discovery path, lists tools, and verifies that production deployment is human-gated.

## From Hermes

In a profile where the plugin is enabled, ask Hermes to use the Company Layer, for example:

```text
Use the ThinkToFinish company tools and show company status.
```

Then try a policy decision:

```text
Check whether production_deployment with medium risk may proceed autonomously.
```

Expected decision: `human_approval`.

---

# How to use the governance tools in a real project

## 1. Validate a task contract

Before a worker starts a meaningful engineering task, give it a contract such as:

```yaml
id: HRMS-EMP-014
title: Implement Employee API
goal: Enforce employee CRUD and RBAC from the approved Product Spec.
inputs:
  - PRD v1
  - ADR-004
outputs:
  - production code
  - unit tests
  - integration tests
acceptance_criteria:
  - HR can create and update employees
  - Manager can view only their team
  - Employee can view self
  - Unauthorized access returns 403
verification:
  - pytest tests/employees
  - ruff check .
  - mypy src
risk: medium
assignee_role: engineer
review:
  required: true
  profile: qa-reviewer
security:
  required: true
  profile: qa-reviewer
traceability:
  requirement_ids:
    - HRMS-REQ-EMP-001
```

The worker/orchestrator should call `ttf_validate_task_contract` before execution.

## 2. Check high-risk actions

Before performing an action with business/security impact, call `ttf_policy_check`.

Default V0.1 policy includes:

**Autonomous**
- research
- requirements
- product specification
- architecture
- coding/testing/documentation
- branch/PR creation
- staging deployment

**Human approval**
- production deployment
- destructive DB migration
- credential change
- paid service purchase
- major scope change
- security exception
- production DB write

**Forbidden**
- direct push to main
- bypass required review
- disable security controls
- expose credentials

A high/critical risk classification upgrades an otherwise autonomous action to a human approval gate.

## 3. Build traceability as work completes

Record nodes and links progressively:

```text
Requirement HRMS-REQ-LEAVE-001
   ↓ implemented_by
Task K-132
   ↓ delivered_by
PR #57
   ↓ verified_by
Test T-221
   ↓ included_in
Release v0.1.0-rc1
```

At release time, call `ttf_requirement_coverage`. A requirement is fully covered only when a path exists to **Task, PR, Test, and Release**.

## 4. Run the release gate

A release candidate requires evidence including:

- CI = pass
- tests = pass
- independent review = approved
- security review = pass
- zero Critical findings
- zero High findings
- traceability complete
- residual risks explicitly declared

A production target additionally requires human approval for `production_deployment`.

## 5. Record learning metrics

Record terminal task metrics and use `ttf_metrics_summary` to watch:

- Average cycle time
- Average retries
- Human interventions
- Cost per completed workstream
- First-pass rate
- Autonomous Completion Rate

The target over repeated projects is:

```text
Autonomous Completion ↑
First-pass rate        ↑
Cycle time             ↓
Retries                ↓
Human interventions    ↓
Escaped defects        ↓
```

---

# Data and security

## Where data is stored

The portable MCP server receives a profile-scoped `PLUGIN_DATA` directory from Hermes. ThinkToFinish stores its SQLite evidence database there as `company.db`.

When running `server.py` directly outside Hermes, it falls back to `.local-data/company.db` inside the repo.

## Secrets

Do **not** put credentials in:

- `plugin.json`
- `mcp.json`
- task contracts
- traceability metadata
- release evidence
- metric metadata

Store identifiers/pointers and redacted summaries instead.

## Profiles are not sandboxes

Do not assume separate Hermes Profiles prevent filesystem access. For sensitive roles, use an isolated terminal backend such as Docker/cloud sandbox or the Codex workspace sandbox, and use role-specific credentials.

## Production rule

V0.1 deliberately ends the autonomous pilot at **Release Candidate**. Production deployment is human-gated by default.

---

# Policy files

Runtime policy source-of-truth in V0.1 is the JSON set:

```text
policies/company.json
policies/autonomy.json
policies/quality.json
policies/security.json
```

The adjacent `.yaml` files are human-readable mirrors/examples. If you customize policy in V0.1, update the JSON file used at runtime as well.

This zero-dependency design is intentional so the portable MCP server can start from system Python without needing PyYAML or a package install.

---

# Local development

Run tests:

```bash
PYTHONPATH=. python3 -m pytest -q
```

Run MCP smoke test:

```bash
python3 scripts/mcp-smoke.py
```

Run the server manually:

```bash
./scripts/run-mcp.sh
```

The server speaks JSON-RPC/MCP over stdio; normal log/protocol-unrelated text must never be printed to stdout.

---

# Installing after this repo is published to GitHub

Once the repo is hosted, each profile can install it through Hermes' normal plugin workflow:

```bash
hermes -p orchestrator plugins install OWNER/thinktofinish-company --enable
hermes -p product plugins install OWNER/thinktofinish-company --enable
hermes -p architect plugins install OWNER/thinktofinish-company --enable
hermes -p engineer plugins install OWNER/thinktofinish-company --enable
hermes -p qa-reviewer plugins install OWNER/thinktofinish-company --enable
hermes -p release-manager plugins install OWNER/thinktofinish-company --enable
```

Until then, `scripts/install-local.sh` performs the equivalent local installation for this source tree.

---

# V0.1 scope boundary

V0.1 intentionally **does not** rebuild capabilities Hermes already owns:

- No custom graph engine
- No custom dispatcher/scheduler
- No custom Agent runtime
- No custom worktree manager
- No custom Goal loop
- No new Kanban dashboard
- No replacement memory/skill system

Instead:

> **Portable First, Native Only When Necessary.**

Hermes Auto Decompose remains useful for ad-hoc Triage work. The default ThinkToFinish pilot deliberately uses a governed orchestrator kickoff plus a second post-architecture planning gate so contracts, review roles, and release gates are explicitly represented in the graph.

Hermes owns Workforce + Workflow + Execution + Learning Infrastructure.
ThinkToFinish owns Governance + Product Lifecycle + Evidence + Accountability.

## Planned V0.2+

Good next additions after V0.1 pilot evidence proves the need:

1. Optional native Hermes hooks to ingest Kanban claimed/completed/blocked events automatically into company metrics.
2. GitHub PR/CI evidence bridge to auto-link Task → Commit → PR → Checks.
3. Company KPI dashboard tab for Autonomous Completion Rate, first-pass rate, retry/cost trends, and release readiness.
4. Stronger release governance with signed evidence snapshots.
5. Policy compiler so human-friendly YAML can become validated immutable runtime policy.

Do not add these until the native Hermes + V0.1 pilot identifies a real gap.

---

# Definition of success for the first pilot

The AI Software Company V1 is working when one root goal can autonomously progress to a Release Candidate while demonstrating all of the following:

1. Natural-language goal accepted.
2. Goal decomposed into a dependency graph.
3. Tasks routed to appropriate Profiles.
4. Independent tasks run in parallel.
5. Engineering changes use isolated branches/worktrees.
6. Engineering loops continue until deterministic gates pass.
7. Independent reviewer can reject and trigger repair.
8. Security and CI evidence pass.
9. Requirement → Task → PR → Test → Release traceability is complete.
10. The Owner intervenes only for business/high-risk decisions.

That is the first measurable step from **AI coding assistant** to **AI Software Company**.
