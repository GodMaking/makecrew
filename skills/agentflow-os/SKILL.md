---
name: agentflow-os
description: Compatibility entry for MakeCrew, an adaptive open-source AI work framework that clarifies vague requests, matches installed Skills and methods, routes work to the right Agent, preserves project memory, verifies delivery, controls cost, and learns from evidence.
---

# AgentFlow OS Compatibility Entry

This legacy Skill ID delegates to MakeCrew. Use it when a user wants AI to clarify an underspecified task, discover
the best available Skill or method, route work to one or more Agents, preserve
project memory, enforce verification, resume interrupted work, or improve from
feedback. Search aliases: `MakeCrew`, `AI Company OS`, `AI work operating
system`, `multi-agent orchestration`, `agent routing`, and `Skill discovery`.

## Default path

Keep one clear task in the current conversation. Ask only the missing questions
that change the deliverable (0-N total, 1-3 per round), then inspect installed
Skill metadata and local methods. Use local matches directly. Search external
candidates only for unresolved capability gaps or a requested fresh comparison;
show purpose, source, license, and trade-offs before the user chooses whether to
install or use one.

## Post-install welcome

After installation or first activation, immediately tell the user in plain
language that MakeCrew is ready and explain the three ways to use it:
lightweight current-conversation mode, approved basic-team mode, and on-demand
employee mode. Mention that existing conversations and project memory are kept,
that a single clear task stays in the current conversation, and that missing
employees are proposed with reasons before creation. Show this welcome once per
workspace and do not send recurring daily notices.

## Employee creation gate

A fresh install loads role templates but creates no employee conversations.
Existing ordinary conversations, employees, project memory, and configuration
remain untouched. When no suitable employee exists, return an
`employee_proposals` list with:

- reason and responsibilities;
- required Skills and tools;
- memory scope;
- estimated Token/time cost;
- workspace and conversation impact.

Set status to `awaiting_employee_approval`. Create or bind an employee
conversation only after explicit user approval. `CEO-001`, `PM-001`, and
`QA-001` are optional templates; a single task does not require a CEO.

## Multi-task path

Use CEO/PM scheduling only when the user submits multiple tasks, asks for
parallel work, or needs cross-project resource decisions. Reuse an approved
employee thread for the same project; propose missing roles first, then dispatch
independent tasks with explicit dependencies, budgets, and one QA summary.

## Verification and learning

Return the route, employee IDs, selected Skills/tools, project context,
acceptance gates, budget, evidence, blockers, and next action. Do not claim a
host-side action without execution evidence. Trigger self-evolution only after
negative feedback, failed verification, rework, repeated issues, or an explicit
retrospective; replay a candidate against a baseline before adoption.

## Compatibility

The legacy Skill path `skills/makecrew/SKILL.md`, Skill ID `makecrew`, command
`makecrew`, Python module `ai_company_os`, and workspace directory `.makecrew`
remain supported.
