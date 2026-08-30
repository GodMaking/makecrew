---
name: makecrew
description: Compatibility entry for AgentFlow OS (formerly MakeCrew), an adaptive AI work operating system for requirement clarification, local-first Skill discovery, Agent routing, project memory, review gates, resumable task state, and evidence-based self-evolution.
---

# MakeCrew Compatibility Skill for AgentFlow OS

Use this skill when a user wants an AI work operating system to clarify vague requests, discover Skills and methods, coordinate coding/research/content/design work, preserve project context, reduce repeated conversation history, or add review and budget controls. The legacy Skill ID is `makecrew`.

For a single new task, prefer the companion `task-intake` Skill. It selects the
shortest reliable path in the current conversation: routine tasks execute
directly, while clarification, discovery, confirmation, an expert panel, and
learning are added only when triggered. Keep AgentFlow OS's CEO/orchestrator path
for explicit multi-task parallel work or cross-project decisions.

For every clear task, inspect and match the host's installed Skills first. Use
local matches directly. Search external candidates for missing capabilities,
show their purpose and source, and wait for the user's install/use choice before
the host changes its Skill inventory.

## Setup

1. Read `README.md`, `docs/getting-started.md`, `docs/platform-adapters.md`, and `docs/skill-card.md`.
2. Inspect `roles/` and `templates/` before creating any new employee.
3. Run `makecrew init --path WORKSPACE --project PROJECT` or call `initialize_workspace()`.
4. Run `makecrew audit --tools TOOL1,TOOL2` and report missing capabilities before execution.
5. Preserve existing ordinary conversations, employee conversations, project memory, and configuration; add only missing files. Load templates without creating employees.

The minimum operating loop is three optional templates: `CEO-001`, `PM-001`,
and `QA-001`. Specialist roles are optional templates. When a role is missing,
first show an `employee_proposals` item with its reason, responsibilities,
Skills, tools, memory scope, estimated cost, and impact. Wait for explicit user
approval before creating an employee or conversation. Never create a large
fixed roster just to make the team look complete.

## Operating loop

Route the task, assign a unique employee ID, pass the smallest useful context, record task state and usage, collect evidence, and send a delta handoff. Use `CrewOrchestrator` (or an equivalent host adapter) to dispatch the payload to the real employee conversation. If no matching profile exists, return an employee proposal and wait for approval; promote only when repeated work justifies it. Public or irreversible actions require user confirmation.

For an explicit multi-task request, use `BatchScheduler`: register tasks in
dependency order, call `dispatch_ready()`, and report one compact overview.
Set `max_concurrency` and an optional `total_tool_calls`; use per-task budgets
to keep a batch within cost. Reuse the `(employee_id, project)` thread before
opening a conversation. `pause`, `resume`, `cancel`, and `mark_failed` preserve
state and reasons. The scheduler is a queue/state kernel; the host adapter must
perform actual conversation creation and tool execution.

## Learning loop

On negative feedback, failed verification, rework, repeated issues, or an
explicit retrospective request, record score, feedback, and root cause with
`LearningEngine`. Generate a proposal, replay it against representative tasks,
and adopt it only when the candidate score improves the baseline. Routine
successful tasks do not pay a mandatory learning round.

## Output contract

Report route, employee IDs, required tools, project context, acceptance gates, budget, status, evidence, blockers, and next action. Avoid claiming tool execution when the host platform did not run it.
