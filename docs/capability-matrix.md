# Employee Capability Matrix / 员工能力矩阵

MakeCrew uses a small, auditable matrix instead of installing every skill on
every employee. The source of truth is `ai_company_os/capabilities.py`; the
workspace registry receives the same `skill_ids` during `init` or additive
upgrade.

## Built-in employees

| Employee | Focus | Required skill groups |
|---|---|---|
| `CEO-001` | Cross-project goals and resource decisions | intake, interview, planning, context, completion verification |
| `PM-001` | Project decomposition and coordination | intake, planning, parallel dispatch, context, completion verification |
| `QA-001` | Independent acceptance | intake, verification, TDD, debugging, context |
| `ENG-001` | Engineering delivery | intake, TDD, debugging, frontend, API, Git, CI/CD, launch, context |
| `RES-001` | Research and evidence | intake, source-driven research, context, verification |
| `CON-001` | Content and copy | intake, interview, source-driven research, context, verification |
| `DES-001` | UI and visual delivery | intake, frontend UI, context, verification |
| `KNO-001` | Knowledge-base processing | intake, source-driven research, context, verification |
| `SKL-001` | Skill creation and maintenance | MakeCrew, intake, interview, context, verification |

The local `skills/` directory contains portable adapters for every ID in the
matrix. They are deliberately short: the host platform can substitute a
newer compatible implementation without changing employee routing or memory.

## GitHub sources reviewed

The workflow ideas were compared against these active public repositories:

- [obra/superpowers](https://github.com/obra/superpowers) (MIT): parallel
  dispatch, test-driven development, and verification-before-completion.
- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (MIT):
  requirements interview, planning, source-driven development, frontend/API,
  Git, CI/CD, and launch workflows.
- [agentskills/agentskills](https://github.com/agentskills/agentskills) (Apache-2.0):
  portable `SKILL.md` format and progressive disclosure specification.

We use the first two as workflow references and keep the third as the format
reference. No external repository is executed or silently copied at install
time. Each source, license, and rationale is machine-readable in
`UPSTREAM_SOURCES`.

## Audit

Run:

```bash
makecrew capability-audit
```

The command reports employees, required IDs, missing local `SKILL.md` files,
unknown IDs, bundled skills, and source metadata. A clean audit has empty
`missing_profiles`, `missing_skill_ids`, and `unknown_skill_ids` arrays.
