---
name: parallel-dispatch
description: Dispatch two or more independent tasks concurrently while preserving isolation, dependencies, budgets, and a compact status summary.
---

# Parallel Dispatch

Use only for explicitly multi-task work. Group tasks by independent domain,
keep shared-state tasks sequential, and assign one employee per task. Pass the
minimum context, cap concurrency and tool calls, and reuse the same
employee/project thread for follow-up work. Collect results, run the shared QA
gate, and report one status table. A failed dependency blocks downstream work.
