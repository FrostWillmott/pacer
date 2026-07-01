---
name: workflow-scaffolding
description: Set up verification tooling for a new Python project — linter, formatter,
  type checker, pre-commit hooks, Makefile, and a single verify-all entry point.
when_to_use: starting a new project, scaffold tooling, add pre-commit hooks, new repository
  setup, project lacks linter or type checker, missing Makefile or CI configuration
---

# Scaffold project verification tooling

When a repo lacks verification infrastructure, set it up before feature work. Ask before
adding anything heavy. Infer specifics from the stack — don't cargo-cult the reference
shape below if the project already has conventions.

## Enforcement hierarchy (strongest first)

CI > pre-commit hooks > `make check` task runner > rules in `.claude/rules/` > prose in CLAUDE.md

Push every rule as high as it goes. A check that only exists in CLAUDE.md prose will
eventually be skipped.

## Steps

1. **Formatter + linter** — for Python: create `ruff.toml` in root (separate from
   `pyproject.toml` so it versions independently). Use `select` (not `extend-select`)
   and set `target-version` explicitly.

2. **Type checker** — for Python: `mypy` with `strict = true` in `pyproject.toml`
   under `[tool.mypy]`.

3. **Pre-commit hooks** — create `.pre-commit-config.yaml` wiring ruff and mypy to run
   before each commit. Do not add tests here — tests belong in CI.

4. **Task runner entry point** — create (or update) `Makefile` with:
   - `make install` — install dependencies + pre-commit
   - `make install-hooks` — `uv run pre-commit install`
   - `make check` — lint + format-check + typecheck + tests
   - `make fix` — ruff --fix + format
   Tell the user to run `make install && make install-hooks` once.

5. **CI** — if the repo is hosted, add a workflow running `make check` on push.

6. **CLAUDE.md** — record the verify command so the agent always knows the entry point:
   ```
   ## Commands
   make check   # lint + format + types + tests — run before finishing any task
   make fix     # auto-fix lint and format issues
   ```

## Reference shape (Python / uv — verify versions before use)

**.pre-commit-config.yaml**
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.1
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy
        language: system
        types: [python]
        pass_filenames: false
```

Run `pre-commit autoupdate` after copying to refresh pinned revisions.

**pyproject.toml** (mypy section)
```toml
[tool.mypy]
strict = true
```

## Path-scoped rules

After copying rule modules into `.claude/rules/`, consider adding `paths:` frontmatter
to modules that only apply to part of the codebase (e.g. `postgresql-pgvector.md` scoped
to `src/db/**`). See `workflow-scaffolding.md` in the rules-library for a mapping table.
