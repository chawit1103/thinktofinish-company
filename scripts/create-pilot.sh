#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="${1:-}"
BOARD="${2:-mini-hrms}"

if [[ -z "$PROJECT_DIR" ]]; then
  echo "Usage: $0 /absolute/path/to/git-project [board-slug]" >&2
  exit 2
fi
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Target must be a Git repository: $PROJECT_DIR" >&2
  exit 1
fi
if ! git -C "$PROJECT_DIR" rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "Target Git repository needs at least one commit before Hermes can create worktrees." >&2
  exit 1
fi
if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed or not on PATH." >&2
  exit 1
fi

if command -v omh >/dev/null 2>&1; then
  WORK_LAYER_NOTE="Oh My Hermes is available. Use OMH for interview/research/planning/work coordination/coding-owner handoffs where useful, while preserving TTF company authority."
else
  WORK_LAYER_NOTE="Oh My Hermes is not available. Use Hermes-native capabilities without changing TTF company policy, task contracts, traceability, or release gates."
  echo "Warning: OMH is not on PATH; the pilot will use the Hermes-native fallback." >&2
  echo "Recommended setup: $ROOT/scripts/bootstrap-company.sh" >&2
fi

if [[ ! -f "$PROJECT_DIR/.hermes.md" && ! -f "$PROJECT_DIR/HERMES.md" && ! -f "$PROJECT_DIR/AGENTS.md" && ! -f "$PROJECT_DIR/CLAUDE.md" && ! -f "$PROJECT_DIR/.cursorrules" ]]; then
  cp "$ROOT/templates/PROJECT_AGENTS.md" "$PROJECT_DIR/AGENTS.md"
  echo "Installed project constitution template: $PROJECT_DIR/AGENTS.md (not auto-committed)"
else
  echo "Existing project context detected; ThinkToFinish did not overwrite it."
  echo "Reference template if you want to merge rules: $ROOT/templates/PROJECT_AGENTS.md"
fi

hermes kanban boards create "$BOARD" \
  --name "Mini HRMS Pilot" \
  --description "ThinkToFinish Company Core + OMH + Hermes pilot" \
  --icon "🏗️" \
  --switch 2>/dev/null || hermes kanban boards switch "$BOARD"

hermes kanban boards set-default-workdir "$BOARD" "$PROJECT_DIR"

IFS= read -r -d '' ROOT_BODY <<BODY || true
You are the ThinkToFinish company orchestrator. PLAN AND DISPATCH company phases; do not implement production code on this kickoff card.

Layer authority:
- ThinkToFinish owns WHAT/WHY: business scope, Product Spec, requirement IDs, Architecture Contract/ADRs, Company Task Contracts, policy, traceability, risk/approval, release governance, and company metrics.
- Oh My Hermes owns HOW TO ORGANIZE WORK when available: interview/research/planning, work coordination, coding-owner selection/handoff, long-horizon workflow memory, and execution observations.
- Hermes owns HOW TO RUN IT: Profiles, Kanban, goals/loops, native review/rework, delegation, sessions, plugins, worktrees/sandbox, gateway, and cron.
- Coding owners own implementation and review fixes.

Work-layer status:
$WORK_LAYER_NOTE

Business goal:
Deliver a Release Candidate for a Mini HRMS serving Thai SMEs (50-500 employees).

MVP scope:
- Authentication
- Employee management
- Leave request and approval
- RBAC for HR, Manager, Employee
- Basic audit log
- Minimal dashboard

Out of scope:
- Payroll (Phase 2)
- Production deployment

Company constraints:
- Use ThinkToFinish policy, task-contract, traceability, release-gate, and metrics tools.
- Create stable requirement IDs before implementation.
- Product may use OMH `ulw-interview` / `ulw-research`; the TTF Product Spec remains authoritative.
- Architecture may use OMH research/planning; accepted ADRs/contracts remain TTF authority.
- Engineering may use OMH to organize work and select/prepare coding-owner handoffs. Never weaken the Company Task Contract to fit a workflow/executor.
- Use Hermes native same-card implementation review. A ready producer calls `kanban_request_review(..., reviewer="qa-reviewer")`; the reviewer approves or calls `kanban_request_changes(reason=...)` to return work to the original implementer.
- Do NOT create a pre-created review child for the same implementation phase. Do NOT use `kanban_block` or the legacy TTF transition engine for ordinary review feedback.
- Keep integrated QA/Security and Release Evidence as separate downstream company gates.
- Production deployment, destructive migrations, credentials, paid services, major scope changes, production DB writes, and security exceptions require human approval.
- Direct push to main, bypassing required review, disabling security controls, and exposing credentials are forbidden.

Required staged graph:
1. Create Product Discovery / Product Spec assigned to `product`, goal_mode=true. It must create stable requirement IDs, explicit acceptance criteria, scope/non-scope, risks/assumptions, and requirement traceability nodes. It may use OMH interview/research but must output a TTF Product Spec.
2. Create Architecture Contract assigned to `architect`, parented on Product, goal_mode=true. It must create ADRs, API/data/security boundaries, a shared Decision Packet, verification plan, and requirement→ADR trace links. It may use OMH research/planning but must output a TTF Architecture Contract.
3. Create a second orchestrator planning card assigned to `orchestrator`, parented on Architecture, goal_mode=true, titled roughly "Plan and dispatch Mini HRMS engineering work packages". That card must read Product + Architecture handoffs and create the concrete company graph:
   - 2-4 meaningful implementation work packages assigned to `engineer` where architecture permits;
   - each implementation task has a validated Company Task Contract and uses Hermes native same-card review with `qa-reviewer`;
   - OMH may organize implementation/coding-owner handoffs inside each work package, but the Kanban board must not mirror OMH internal sub-work card-for-card;
   - one integration work package gated on the reviewed/done implementation tasks, also using native same-card review;
   - one independent integrated QA/Security company card assigned to `qa-reviewer` gated on reviewed integration;
   - one Release Evidence card assigned to `release-manager` gated on QA/Security;
   - one Company Closeout card assigned to `orchestrator` gated on Release Evidence.
4. The final Company Closeout must call ThinkToFinish coverage/release tools and may declare only Release Candidate readiness. OMH QA success, green CI, or Hermes task completion alone is not sufficient.
5. Complete this kickoff after the Product, Architecture, and second orchestrator planning cards plus their dependencies exist. Include created card IDs and summarize the company graph.

Do not create custom schedulers, remediation graphs, memory engines, executor routers, or Kanban database transitions. Prefer native OMH/Hermes contracts.
BODY

hermes kanban create "Orchestrate Mini HRMS to Release Candidate" \
  --assignee orchestrator \
  --goal \
  --goal-max-turns 10 \
  --max-retries 3 \
  --body "$ROOT_BODY"

echo
echo "ThinkToFinish pilot kickoff created on board: $BOARD"
echo "Project directory: $PROJECT_DIR"
echo "Board default workdir: $PROJECT_DIR"
echo "Keep/start gateway: hermes -p orchestrator gateway start"
echo "Open dashboard: hermes dashboard"
echo "Expected company flow: Product → Architecture → Engineering Work Packages → Integration → QA/Security → Release Evidence → RC."
