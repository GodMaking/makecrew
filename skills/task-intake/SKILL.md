---
name: task-intake
description: Use before executing a new project, website, app, product, video, document, campaign, automation, materially ambiguous request, or multi-task batch; clarify missing requirements, present a plan when needed, match installed Skills and local methods, then execute only after the applicable confirmation gate.
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
   - every clear task: match required capabilities against installed Skills and local methods;
   - missing local capability or fresh research/comparison need: expand discovery;
   - explicit plan-first request or consequential action: present a brief and wait;
   - one multi-domain task: form an implicit expert panel in this conversation;
   - several submitted tasks: use CEO batch mode.
2. When questions are needed, prefer deliverable, existing project/path, target
   user, constraints, success criteria, or deadline. Total questions are 0-N,
   with one to three per round. Stop when material gaps are resolved or the user
   delegates remaining details to AI defaults.
   Give each gap a stable ID, prompt, and reason. Merge domain-specific gaps
   from the current model with the built-in gaps; skip IDs already answered.
3. For every decision-ready task, inspect the host's installed Skill inventory
   and match it to the task, tools, and acceptance checks. Use matching local
   Skills directly. When required capability IDs are missing, search external
   candidates and present each candidate's purpose, source, and trade-offs.
   Ask the user whether to install/use a candidate or continue with current
   capabilities. After installation, refresh the local inventory before work.
   Match local methods on every clear task; expand external method search when
   the user needs a fresh comparison, the local catalog has no match, or a
   capability gap remains. Prefer primary sources and label local versus fresh.
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

For a new or substantially redesigned website, app, product, or multi-stage
feature, select `product-delivery` after intake. It adds a project brief,
prototype/demo, technical design, and implementation gate; small maintenance
tasks remain on the direct path.

The host should provide its installed Skill IDs and may provide both
`skill_searcher(task, missing_skill_ids)` and `method_searcher(task, domains)`
adapters. Local matching is automatic after clarification. External search is
gap-driven or freshness-driven. Keep candidates pending until the user chooses
and the host confirms installation or availability.

## Batch mode: explicit multi-task request

Use batch mode only when the user supplies multiple independent tasks in one
request or explicitly asks the CEO to coordinate several tasks. Then:

1. CEO classifies each task and creates a minimal task packet.
2. Reuse registered employee conversations first.
3. If a task has no suitable employee, first propose the missing employee with
   its reason, responsibilities, required Skills, tools, memory scope,
   estimated cost, and impact. Create the employee conversation only after
   explicit user approval.
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
