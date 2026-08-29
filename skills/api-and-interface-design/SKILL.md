---
name: api-and-interface-design
description: Define stable API and module contracts before implementation, including validation and error semantics.
---

# API And Interface Design

Write the input, output, invariants, versioning, and failure contract first.
Validate at boundaries and keep one canonical representation of each field.
Check compatibility with existing callers and add contract tests before
changing behavior. Document the reason for breaking or extending a public
interface.
