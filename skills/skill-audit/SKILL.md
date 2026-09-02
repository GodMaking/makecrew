---
name: skill-audit
description: Use when reviewing, installing, updating, or publishing an Agent Skill; validate SKILL.md metadata, trigger keywords, naming, compatibility, references, scripts, and progressive disclosure before activation.
---

# Skill Audit

Treat a Skill as an executable capability contract, not just a prompt file.

1. Inspect `SKILL.md` frontmatter before reading references or scripts.
2. Require a unique lowercase hyphenated `name`, a useful `description` that
   states what it does and when it triggers, and a directory-name match.
3. Keep the main instructions short; put large references, scripts, and assets
   in separate directories and load them only after a task matches.
4. Record source, version, license, compatibility requirements, and local
   installation path. Do not silently replace an existing Skill.
5. Test one positive trigger, one near miss, and one missing-resource path.
   Report issues with a stable code and the exact file path.

Use `makecrew skill-audit --path SKILLS_DIR` for the local structural report.
