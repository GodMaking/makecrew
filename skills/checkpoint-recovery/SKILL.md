---
name: checkpoint-recovery
description: Use when an Agent task can be interrupted, retried, resumed after restart, or needs durable progress without replaying completed model and tool calls.
---

# Checkpoint Recovery

Persist compact state at meaningful workflow boundaries and make host retries
idempotent.

1. Save task ID, node ID, output references, and an idempotency key after each
   completed boundary; never persist full chat history as a checkpoint.
2. On restart, load the latest checkpoint and resume the next uncompleted node.
   Preserve the original task, employee, project, and file scope.
3. Retry only explicitly retryable failures, with a bounded attempt count. A
   retry resumes from the latest checkpoint and records the reason; it does
   not blindly repeat completed side effects.
4. Stop after the retry budget or on a non-retryable failure, then report the
   checkpoint, failure evidence, and next action to the supervisor.

Hosts can use `JsonCheckpointStore` and `RetryPolicy` or provide an equivalent
durable adapter with the same fields.
