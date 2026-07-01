# Workflow scaffolding (apply at project start)

A meta-instruction: when starting work in a repo that lacks verification
scaffolding, set it up before feature work. Describes *intent*, not fixed tools
— infer specifics from the stack so this doesn't go stale as tools change.
Ask before adding anything heavy.

> **Skill alternative:** `project-template` ships a companion
> `.claude/skills/workflow-scaffolding/SKILL.md` that loads this content on
> demand instead of every session. Prefer the Skill in production projects;
> keep this Rule only if you want it always-active.

## Principles (stable; the tools that implement them change)
- Verification must be mechanical, not manual. The environment enforces style
  and types so they never need restating.
- Enforcement hierarchy, strongest first: **CI > pre-commit hooks > a single
  task-runner entry point > prose in CLAUDE.md.** Push every rule as high as it goes.
- One command verifies everything (lint + types + tests). Run it after any
  change; fix until green before handing back.

## On project start, ensure these exist (create if missing; infer specifics):
- A formatter + linter with its config in a standalone file (for Python:
  `ruff.toml` in root, separate from `pyproject.toml`).
- Static type checking where the language supports it (for Python: mypy, strict).
- A pre-commit mechanism wiring the above to run before each commit.
- A single verify-all entry point (`make check` / `just check` / a script) that
  runs lint + types + tests.
- CI running that same entry point on push, if the repo is hosted.

## Rules
- Record/pin tool versions in the project's lockfile or config, not from memory.
  Verify current versions rather than assuming — config syntax drifts between
  versions (ruff rule codes, pre-commit hook revs).
- Tell the user any one-time activation step they must run themselves
  (e.g. `pre-commit install` / `make install`).
- Don't silently impose a toolset on an existing repo with its own conventions —
  match what's there, or ask.

## Reference shape (Python/uv — regenerate against current versions)
- `ruff.toml`: `select`-based explicit rule set, explicit `target-version`.
- `.pre-commit-config.yaml`: ruff (lint+format) and mypy hooks; check `rev`s are current.
- `Makefile`: `install`, `fix`, `lint`, `type`, `test`, `check` targets.
- `pyproject.toml`: `[tool.mypy] strict = true` (mypy reads pyproject, ruff its own file).

## Path-scoped rules  [PREFER]

Rules in `.claude/rules/` support YAML frontmatter with a `paths` field. The rule
loads only when Claude works with a file matching the pattern — reducing noise and
saving context tokens for modules that are not always relevant.

```markdown
---
paths:
  - "src/db/**/*.py"
  - "infrastructure/**/*.py"
---
# PostgreSQL & pgvector conventions
...
```

Suggested path-scope for library modules (adapt to project layout):

| Module | Suggested paths pattern |
|--------|------------------------|
| `postgresql-pgvector.md` | `src/db/**`, `infrastructure/**`, `**/repositories/**` |
| `data-engineering.md` | `src/pipelines/**`, `etl/**`, `**/jobs/**` |
| `clean-architecture.md` | entire project (if applied, it's always relevant) |
| `ai-engineering.md` | `src/llm/**`, `src/ai/**`, `**/prompts/**` |

Module files in `rules-library/` intentionally omit `paths:` — paths are
project-specific and must be set when copying a module into `.claude/rules/`.
