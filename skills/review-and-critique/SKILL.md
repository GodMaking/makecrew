---
name: review-and-critique
description: Use when a code task reaches a meaningful milestone, before merging or publishing, or when an independent check is needed to find requirement, regression, test, or security issues.
---

# Review And Critique

Review the change against the task contract, not against personal preference.

1. Read the task goal, acceptance gates, changed files, and fresh test output.
2. Check behavior, edge cases, regressions, error handling, security, and
   maintainability. Inspect the smallest relevant diff; do not copy full
   employee histories into the review context.
3. Report findings first, ordered by severity, with file and line evidence and
   a concrete fix. Separate open questions from confirmed findings.
4. A critical or important finding blocks delivery until fixed or explicitly
   adjudicated. Re-run the focused check after each fix and the full suite
   before merge.

For a routine read-only query, skip this Skill. Use it at milestones so review
cost buys a measurable quality signal rather than another full conversation.
