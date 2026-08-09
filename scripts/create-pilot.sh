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

# Install a project constitution only when the repo has no supported project context file.
# Never overwrite a user's existing instructions.
if [[ ! -f "$PROJECT_DIR/.hermes.md" && ! -f "$PROJECT_DIR/HERMES.md" && ! -f "$PROJECT_DIR/AGENTS.md" && ! -f "$PROJECT_DIR/CLAUDE.md" && ! -f "$PROJECT_DIR/.cursorrules" ]]; then
  cp "$ROOT/templates/PROJECT_AGENTS.md" "$PROJECT_DIR/AGENTS.md"
  echo "Installed project constitution template: $PROJECT_DIR/AGENTS.md (not auto-committed)"
else
  echo "Existing project context detected; ThinkToFinish did not overwrite it."
  echo "Reference template if you want to merge rules: $ROOT/templates/PROJECT_AGENTS.md"
fi

hermes kanban boards create "$BOARD" \
  --name "Mini HRMS Pilot" \
  --description "ThinkToFinish AI Software Company V1 pilot" \
  --icon "🏗️" \
  --switch 2>/dev/null || hermes kanban boards switch "$BOARD"

# Hermes latest supports a per-board default project directory. With a Git repo,
# this lets dispatched tasks use preserved worktree workspaces instead of racing
# one shared checkout.
hermes kanban boards set-default-workdir "$BOARD" "$PROJECT_DIR"

ROOT_BODY=$(cat <<'BODY'
You are the ThinkToFinish company orchestrator. Your job on this card is to PLAN AND DISPATCH the project graph, not to implement production code.

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
- Producer and independent reviewer must be separate roles.
- Engineering work uses the board-linked Git project/worktrees and PRs; never push directly to main.
- Engineering tasks use goal_mode when iterative implementation/verification is needed.
- Production deployment, destructive migrations, credentials, paid services, major scope changes, production DB writes, and security exceptions require human approval.
- Direct push to main, bypassing review, disabling security controls, and exposing credentials are forbidden.

Required orchestration pattern:
1. Create a Product Discovery / Product Spec card assigned to `product`, goal_mode=true. It must produce stable requirement IDs and explicit acceptance criteria, and record requirement traceability nodes.
2. Create an Architecture Contract card assigned to `architect`, parented on the Product card, goal_mode=true. It must produce ADRs, API/data/security boundaries, and a verification plan.
3. Create a second orchestrator card assigned to `orchestrator`, parented on the Architecture card, goal_mode=true, titled roughly "Plan and dispatch Mini HRMS engineering DAG". Its body must instruct that future orchestrator to read Product + Architecture handoffs and then create the concrete engineering graph, including:
   - 2-4 parallelizable implementation cards assigned to `engineer` where architecture permits;
   - an integration card gated on all implementation cards;
   - independent QA/security card assigned to `qa-reviewer` gated on integration;
   - release-evidence card assigned to `release-manager` gated on QA/security;
   - final company closeout card assigned to `orchestrator` gated on release evidence.
   Every implementation card must include a Company Task Contract (goal, inputs, outputs, acceptance criteria, verification, risk, assignee, review/security, requirement IDs). Engineering cards must use goal_mode=true.
4. The final company closeout must check requirement coverage and release evidence using ThinkToFinish tools. It may declare only Release Candidate readiness; production remains human-gated.
5. Complete this kickoff card after those three cards and dependencies have been created. Include the created card IDs in `created_cards` and summarize the graph.

Do not implement the HRMS on this kickoff card. The Definition of Done for this card is a correctly staged project graph that can proceed without further prompting.
BODY
)

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
echo "Keep/start gateway: hermes gateway start"
echo "Open dashboard: hermes dashboard"
echo "The orchestrator kickoff should create Product → Architecture → governed Engineering DAG automatically."
