---
name: task-intake
description: Select the shortest reliable path for a task: execute clear routine work directly, ask only blocking questions, discover methods only when needed, and require confirmation only for plan-first or consequential actions.
---

# Task Intake and Execution

Use this skill as a lightweight router for a new task. Most requests should skip
several stages rather than pass through one fixed pipeline.

## Default: one task, one conversation

Keep the work in the current Codex conversation. Do not create a CEO handoff or
separate employee conversation for an ordinary single task.

1. Classify the request before model-heavy work:
   - clear, routine, reversible: execute now, then verify and deliver;
   - materially ambiguous: ask one to three blocking questions per round and
     continue until the task is decision-ready;
   - explicit research/comparison request or capability gap: discover methods;
   - explicit plan-first request or consequential action: present a brief and wait;
   - one multi-domain task: form an implicit expert panel in this conversation;
   - several submitted tasks: use CEO batch mode.
2. When questions are needed, prefer deliverable, existing project/path, target
   user, constraints, success criteria, or deadline. Total questions are 0-N,
   with one to three per round. Stop when material gaps are resolved or the user
   delegates remaining details to AI defaults.
   Give each gap a stable ID, prompt, and reason. Merge domain-specific gaps
   from the current model with the built-in gaps; skip IDs already answered.
3. Discover methods, workflows, and Skills only when the request asks for fresh
   research/comparison or the current capability set has a real gap. Prefer
   primary sources and label local knowledge versus fresh results.
4. For plan-first or consequential work, present an execution brief:
   - selected skills and tools, with a reason for each;
   - candidate methods and Skills, with evidence and trade-offs;
   - planned workflow and deliverables;
   - acceptance checks and likely risks;
   - files, permissions, or user inputs still needed;
   - expected token/cost controls.
5. Wait for the user's choice and explicit confirmation before high-cost, public, destructive, or
   irreversible actions. A bare “continue” or “execute” confirms the presented brief
   only when no new scope has appeared.
6. Execute in this conversation with the selected skills as soon as the chosen
   path is ready. Routine work has no confirmation round.
   Keep the panel of experts implicit in the current context; do not narrate
   unnecessary internal handoffs or repeat the full history.
7. Finish with evidence, changed files/links, verification, limitations, and
   next action. Do not claim an external action without tool evidence.
8. Trigger learning only after negative feedback, failed verification, rework,
   repeated issues, or an explicit retrospective request.

The host may provide a `method_searcher(task, domains)` adapter for fresh web or
repository research. Calling it is conditional, even when it is available.
Never let a search result silently change scope, install a package, or trigger a
public action.

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
