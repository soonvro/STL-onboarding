# Project Working Rules

This document contains the working rules at the repository root.
If a lower directory has its own `AGENTS.md`, it takes precedence in that scope.

## Justfile-first rule

- Project execution commands should be run through `Justfile` by default.
- For the following tasks, verify that an appropriate recipe exists in `Justfile` first:
  - running tests
  - dependency installation, sync, and update
  - health checks and status checks
  - deployment, release, and operational commands
- If a suitable recipe exists, do not run raw commands directly; always use `just <recipe>`.
- If no suitable recipe exists, do not perform a one-off workaround. Add a reusable recipe to `Justfile` first, then use that recipe.
- Recipe names should be descriptive of their role. e.g. `test`, `deps-install`, `deps-update`, `health-check`, `deploy`.
- Once a consistent recipe set is in place, follow the same structure for new recipes.
- Avoid applying this rule too rigidly to non-operational work such as exploration or file inspection.

## ADR request handling

- If the user requests ADR creation, check `docs/adr/AGENTS.md` before starting.
- ADR filename rules, template usage, document language, status labels, and index update rules follow `docs/adr/AGENTS.md` exclusively.
- When creating or modifying ADRs, manage `docs/adr/000_index.md` together.

## Architecture discussion handling

- If the user asks about architecture, design, technology choices, decisions, or trade-offs, check `docs/adr/AGENTS.md` first.
- Do not end architecture discussions with only a simple answer; evaluate whether an ADR is warranted.
- If the outcome leads to a decision with long-term significance, create or update an ADR following `docs/adr/AGENTS.md`.
- Even if the user did not explicitly request documentation, propose ADR creation/update if decision records are likely needed.

## Priority

- This document applies to repository-wide operations.
- For work inside `docs/adr/`, apply `docs/adr/AGENTS.md` and follow its deeper rules as higher priority.
