---
name: makecrew
description: MakeCrew is an adaptive open-source AI work framework for requirement clarification, local-first Skill discovery, Agent routing, project memory, review gates, resumable task state, and evidence-based self-evolution.
---

# MakeCrew

Use this skill when a user wants an AI work operating system to clarify vague requests, discover Skills and methods, coordinate coding/research/content/design work, preserve project context, reduce repeated conversation history, or add review and budget controls. The legacy Skill ID is `makecrew`.

For a single new task, prefer the companion `task-intake` Skill. It selects the
shortest reliable path in the current conversation: routine tasks execute
directly, while clarification, discovery, confirmation, an expert panel, and
learning are added only when triggered. Keep MakeCrew's CEO/orchestrator path
for explicit multi-task parallel work or cross-project decisions.

For substantial website, app, product, or multi-stage feature work, load the
companion `product-delivery` Skill after intake. It adds a project brief,
prototype/demo, technical design, incremental implementation, and independent
verification before delivery. Small fixes and routine work keep the shorter
path.

For product work, do not move from clarification directly to a bare execution
confirmation. Recalculate all material gaps after every answer (the 1-3 question
display is per round, with no total cap), then show an execution brief containing
selected Skills, tools, methods, workflow, deliverables, acceptance gates,
budget, and risks before asking for approval.

For every clear task, inspect and match the host's installed Skills first. Use
local matches directly. Search external candidates for missing capabilities,
show their purpose and source, and wait for the user's install/use choice before
the host changes its Skill inventory.

After setup or first activation, immediately give the user a plain-language
welcome: say MakeCrew is ready, explain lightweight current-conversation,
approved basic-team, and on-demand employee modes, and state that existing
conversations and project memory remain intact. Show this once per workspace;
do not send recurring daily notices.

Tell the user how to trigger it: automatic matching may load this skill when a
task matches the description; explicit `$makecrew` or `$task-intake` always asks
the host to run intake first. For every new multi-step creation request, explain
that the host will clarify requirements, show selected Skills/tools and a plan,
then wait for the user's approval before execution unless the user says “直接
执行”, “你决定”, or “按默认值执行”.

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

Before dispatching to a busy employee, inspect its active task IDs and locked
paths. Report the conflict and let the user choose `queue`, an isolated
temporary employee/thread, or rerouting to an idle employee. Never merge two
unrelated supervisor histories into one thread; thread identity includes the
supervisor, project, and isolation scope.

For an explicit multi-task request, use `BatchScheduler`: register tasks in
dependency order, call `dispatch_ready()`, and report one compact overview.
Set `max_concurrency` and an optional `total_tool_calls`; use per-task budgets
to keep a batch within cost. Reuse the `(employee_id, project)` thread before
opening a conversation. `pause`, `resume`, `cancel`, and `mark_failed` preserve
state and reasons. The scheduler is a queue/state kernel; the host adapter must
perform actual conversation creation and tool execution.

## Quality and recovery contracts

Use the optional P0 contracts at the boundary where they add evidence:

- run `makecrew skill-audit --path SKILLS_DIR` before publishing or updating a
  Skill; inspect metadata and progressive-disclosure layout without loading
  unrelated resources;
- run `makecrew skill-inventory --path SKILLS_DIR` when the host needs a
  metadata-only local capability list; load matched instructions later;
- invoke `review-and-critique` at meaningful development milestones, before a
  merge, or before a release; keep routine queries on the short path;
- use `checkpoint-recovery` (or an equivalent host adapter) at workflow node
  boundaries so restart resumes compact state through an idempotency key and
  bounded retry policy.

Keep `task_id`, `node_id`, `idempotency_key`, `resume_from`, evidence, and the
failure reason in adapter results. These contracts supplement the scheduler;
they do not create employees, add a mandatory review round, or claim host
execution when callbacks are not connected.

Codex role mapping is direct: the parent/supervisor Agent manages the batch,
each Codex subagent is one MakeCrew employee, and the QA Agent independently
verifies the results. `BatchScheduler.supervisor_id` records the parent Agent;
every dispatch includes an employee `agent_id`, a supervisor identity, and a
compact `task_packet`. When the host supplies
`agent_dispatcher(thread_id, task_packet)`, the packet is handed to the native
Codex Agent. Employees return only `summary`, `evidence`, `risks`, and
`next_steps`; the supervisor uses `aggregate_results()` to synthesize the
user-facing update.

For a concrete Codex host bridge, use `CodexAdapter`: bind its
`spawn_subagent(prompt, metadata)` and `send_to_thread(thread_id, prompt)`
callbacks, pass `open_employee_thread` and `dispatch` to `BatchScheduler`, and
write employee results back with `complete()`. Call `audit()` before starting a
batch. A missing callback leaves work in `queued` state with the exact missing
capability; it never claims that a native Agent was created.

## Learning loop

On negative feedback, failed verification, rework, repeated issues, or an
explicit retrospective request, record score, feedback, and root cause with
`LearningEngine`. Generate a proposal, replay it against representative tasks,
and adopt it only when the candidate score improves the baseline. Routine
successful tasks do not pay a mandatory learning round.

## Output contract

Report route, employee IDs, required tools, project context, acceptance gates, budget, status, evidence, blockers, and next action. Avoid claiming tool execution when the host platform did not run it.
