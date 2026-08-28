---
name: makecrew
description: Set up and operate MakeCrew, an AI Company OS for routing work across AI employees with project memory, review gates, resumable task state, and evidence-based learning.
---

# MakeCrew Skill

Use this skill when a user wants AI to manage a team of AI employees, coordinate coding/research/content/design work, preserve project context, reduce repeated conversation history, or add review and budget controls.

## Setup

1. Read `README.md`, `docs/getting-started.md`, `docs/platform-adapters.md`, and `docs/skill-card.md`.
2. Inspect `roles/` and `templates/` before creating any new employee.
3. Run `makecrew init --path WORKSPACE --project PROJECT` or call `initialize_workspace()`.
4. Run `makecrew audit --tools TOOL1,TOOL2` and report missing capabilities before execution.
5. Preserve existing project memory and employee conversations; add only missing files.

The minimum operating loop is three core roles: `CEO-001`, `PM-001`, and
`QA-001`. Specialist roles are optional templates. Let the user choose the
count per project; duplicate a template when parallel capacity is useful, or
add a custom profile with `makecrew add-employee`. Never create a large fixed
roster just to make the team look complete.

## Operating loop

Route the task, assign a unique employee ID, pass the smallest useful context, record task state and usage, collect evidence, and send a delta handoff. Use `CrewOrchestrator` (or an equivalent host adapter) to dispatch the payload to the real employee conversation. If no matching profile exists, create a temporary employee; promote only when repeated work justifies it. Public or irreversible actions require user confirmation.

## Learning loop

Record score, feedback, and root cause with `LearningEngine`. Generate a proposal, replay it against representative tasks, and adopt it only when the candidate score improves the baseline. Keep proposals versioned and reviewable.

## Output contract

Report route, employee IDs, required tools, project context, acceptance gates, budget, status, evidence, blockers, and next action. Avoid claiming tool execution when the host platform did not run it.
