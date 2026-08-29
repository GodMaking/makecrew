---
name: task-intake
description: Clarify an underspecified task, choose the best available skills and tools, and execute in the current Codex conversation after user confirmation; use CEO fan-out only for explicit multi-task batches.
---

# Task Intake and Execution

Use this skill as the default entry point for a new task.

## Default: one task, one conversation

Keep the work in the current Codex conversation. Do not create a CEO handoff or
separate employee conversation for an ordinary single task.

1. Restate the requested outcome in one sentence.
2. Identify only the missing decisions that could change the implementation.
3. Ask at most three concise questions. Prefer questions about deliverable,
   existing project/path, target user, constraints, success criteria, or deadline.
4. When the request is sufficiently clear, present an execution brief:
   - selected skills and tools, with a reason for each;
   - planned workflow and deliverables;
   - acceptance checks and likely risks;
   - files, permissions, or user inputs still needed;
   - expected token/cost controls.
5. Wait for an explicit confirmation before high-cost, public, destructive, or
   irreversible actions. A bare “继续” or “执行” confirms the presented brief
   only when no new scope has appeared.
6. After confirmation, execute in this conversation with the selected skills.
   Keep the panel of experts implicit in the current context; do not narrate
   unnecessary internal handoffs or repeat the full history.
7. Finish with evidence, changed files/links, verification, limitations, and
   next action. Do not claim an external action without tool evidence.

## Batch mode: explicit multi-task request

Use batch mode only when the user supplies multiple independent tasks in one
request or explicitly asks the CEO to coordinate several tasks. Then:

1. CEO classifies each task and creates a minimal task packet.
2. Reuse registered employee conversations first.
3. If a task has no suitable employee, create only the missing employee
   conversation with a scoped role, required skills, tools, memory scope, and
   acceptance checks.
4. Dispatch independent tasks in parallel and keep dependencies explicit.
5. Return one compact status table and one consolidated QA summary.

Do not route a single task through CEO merely because the task uses several
skills. Several skills can be selected inside the current conversation.

## Confirmation rules

Always surface the target and rollback/verification plan before production
release, public posting, payment, deletion, or other irreversible actions.

## Token rules

- Read only the current project context needed for the task.
- Prefer one compact execution brief over repeated role messages.
- Do not copy complete employee histories into the current conversation.
- Do not create permanent employees for one-off work; use a temporary scoped
  role and promote it only after repeated demand.
