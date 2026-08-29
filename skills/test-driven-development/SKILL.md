---
name: test-driven-development
description: Drive behavior changes through a failing reproduction or test, the smallest implementation, and a regression run.
---

# Test Driven Development

For a bug, first reproduce the reported symptom with a focused test. For new
behavior, define the observable contract first. Implement the smallest change,
run the focused test, then run the relevant full suite. Keep tests isolated and
assert outcomes rather than incidental call order.
