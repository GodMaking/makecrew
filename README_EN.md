# AI Company OS

A lightweight operating system for a one-person AI company: specialists do deep work, project leads coordinate, independent reviewers verify, and the CEO handles cross-project decisions.

## Core flow

```text
User -> specialist (small task)
User -> project lead -> specialists (single-project task)
User -> CEO -> project leads -> specialists (cross-project decision)
```

Use the task card for routing, a project context pack for stable memory, and a delta handoff for collaboration. Keep private conversations, credentials, local paths, and business data out of this repository.

See `docs/` for architecture, routing, and memory rules. Templates are in `templates/`; role prompts are in `roles/`.

Start with `docs/getting-started.md`, copy prompts from `docs/prompt-pack.md`, and choose an adapter from `docs/platform-adapters.md`. The system is model- and vendor-agnostic.

For a complete walkthrough, see `examples/first-task/README.md`. Contributions and security boundaries are documented in `CONTRIBUTING.md` and `SECURITY.md`.

## Runnable MVP

Requires Python 3.10+. No third-party runtime dependency is needed:

```bash
python -m ai_company_os.cli "Build a website, research users, and prepare launch copy" --project demo-site
python -m ai_company_os.web
```

Open `http://127.0.0.1:8787` for the local demo. The router returns a serializable collaboration plan without uploading task text or requiring an API key.
